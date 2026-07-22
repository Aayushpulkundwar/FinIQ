import time
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple, Any
from uuid import UUID
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial import (
    FinancialStatement, FinancialMetric, FinancialEvidence,
    FinancialMetricProvenance, PeriodType
)
from app.repositories.financial import FinancialRepository
from app.repositories.company import CompanyRepository
from app.schemas.financial import (
    FinancialAnalyzeResponse, FinancialStatementData, FinancialMetricsData,
    FinancialFieldEvidence, MetricProvenance as MetricProvenanceSchema, TrendPoint
)
from app.services.retrieval import RetrievalService
from app.schemas.retrieval import RetrievalResponse
from app.services.financial_intelligence.extractor import FinancialExtractor
from app.services.financial_intelligence.parser import FinancialParser
from app.services.financial_intelligence.normalizer import FinancialNormalizer
from app.services.financial_intelligence.validator import FinancialValidator
from app.services.financial_intelligence.calculator import MetricCalculator
from app.services.financial_intelligence.trend_analyzer import TrendAnalyzer


class FinancialIntelligenceService:
    """
    Orchestrates the full Financial Intelligence pipeline:
    Retrieval → Parsing → Validation → Normalization → Persistence → Metrics → Trends

    Supports year fallback and yfinance lookup fallback when no RAG documents are available.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repository = FinancialRepository(db)
        self.company_repo = CompanyRepository(db)
        self.retrieval_service = RetrievalService(db)
        self.extractor = FinancialExtractor(self.retrieval_service)
        self.trend_analyzer = TrendAnalyzer(self.repository)

    async def analyze(
        self,
        company_id: UUID,
        fiscal_year: Optional[int] = None,
        period_type: Optional[str] = None,
    ) -> FinancialAnalyzeResponse:
        """
        Runs the full Financial Intelligence analysis pipeline for a company.
        Resolves year fallback and checks RAG vs live API fallback.
        """
        from app.core.cache import cache

        # Resolve company
        company = await self.company_repo.get(company_id)
        if not company:
            raise ValueError(f"Company with id={company_id} not found.")

        # Determine year fallback by querying available PDF years for this company
        from sqlalchemy import select
        from app.models.document import Document, ProcessingStatus

        stmt = select(Document.fiscal_year).where(
            Document.company_id == company_id,
            Document.processing_status == ProcessingStatus.completed
        ).distinct().order_by(Document.fiscal_year.desc())
        
        res = await self.db.execute(stmt)
        available_years = [r[0] for r in res.fetchall()]

        requested_year = fiscal_year or datetime.now(timezone.utc).year
        resolved_fiscal_year = requested_year
        reporting_status = None
        source_type = "rag"

        if not available_years:
            # No documents exist for this company. Fall back to yfinance
            source_type = "yfinance"
            reporting_status = f"Showing live fallback data for FY{resolved_fiscal_year} (no PDF filings uploaded)."
        elif requested_year not in available_years:
            # Document exists but requested year is missing -> Fall back to latest available year in DB
            resolved_fiscal_year = available_years[0]
            reporting_status = f"Showing FY{resolved_fiscal_year} data; requested FY{requested_year} is not yet available."
            logger.info(f"Fiscal year fallback: requested {requested_year} -> resolved {resolved_fiscal_year}")

        resolved_period_type = PeriodType(period_type) if period_type else PeriodType.annual
        cache_key = f"financial:{company_id}:{resolved_fiscal_year}:{resolved_period_type.value}"
        
        # Check Cache
        cached = await cache.get(cache_key)
        if cached is not None:
            logger.bind(company_id=str(company_id), fiscal_year=resolved_fiscal_year).info(
                "FinancialIntelligenceService.analyze CACHE HIT."
            )
            # Re-insert the dynamic reporting_status which might change depending on requested year
            cached["reporting_status"] = reporting_status
            return FinancialAnalyzeResponse(**cached)

        start_time = time.perf_counter()
        logger.bind(company_id=str(company_id), fiscal_year=resolved_fiscal_year, source=source_type).info(
            "FinancialIntelligenceService.analyze started."
        )

        clean_values: Dict[str, Optional[float]] = {}
        missing_reasons: Dict[str, Any] = {}
        field_evidence_list: List[FinancialFieldEvidence] = []
        chunk_source_map: Dict[str, Optional[RetrievalResponse]] = {}

        if source_type == "yfinance":
            # ── Fallback: yfinance live extraction ──────────────────────────
            logger.info(f"yfinance live fetch for {company.ticker_symbol} (year {resolved_fiscal_year})")
            yfinance_values = await self._fetch_from_yfinance_fallback(
                company.ticker_symbol, company.exchange or "", resolved_fiscal_year
            )
            clean_values = yfinance_values
            from app.services.financial_intelligence.validator import MissingReason
            missing_reasons = {
                field: MissingReason.NOT_REPORTED 
                for field, val in clean_values.items() if val is None
            }
            chunk_source_map = {field: None for field in clean_values.keys()}
        else:
            # ── Standard Pipeline: RAG from database annual report PDFs ──────
            # Note: We query the resolved fiscal year chunks
            logger.info(f"RAG extraction for {company.company_name} (year {resolved_fiscal_year})")
            chunks_by_group = await self.extractor.extract_chunks(company_id=company_id, fiscal_year=resolved_fiscal_year)
            
            # Parse parsed values
            parsed_raw = FinancialParser.parse_chunks(chunks_by_group)
            # parsed_raw: field → (value | None, source_chunk | None)
            raw_string_map = {field: tup[0] for field, tup in parsed_raw.items()}
            chunk_source_map = {field: tup[1] for field, tup in parsed_raw.items()}

            # Normalize values (handles both strings and numbers)
            normalized = FinancialNormalizer.normalize_all(raw_string_map)

            # Validate clean values
            clean_values, missing_reasons = FinancialValidator.validate(normalized)

        # ── Step 5: Persist financial period and statement ──────────────────────
        logger.info("Step 5: Persisting financial period and statement.")
        period = await self.repository.get_or_create_period(
            company_id=company_id,
            fiscal_year=resolved_fiscal_year,
            period_type=resolved_period_type,
        )

        # Upsert FinancialStatement
        stmt_q = select(FinancialStatement).where(
            FinancialStatement.period_id == period.id,
            FinancialStatement.company_id == company_id
        )
        res_stmt = await self.db.execute(stmt_q)
        stmt_db = res_stmt.scalars().first()

        if stmt_db:
            stmt_db.revenue = clean_values.get("revenue")
            stmt_db.ebitda = clean_values.get("ebitda")
            stmt_db.operating_income = clean_values.get("operating_income")
            stmt_db.net_profit = clean_values.get("net_profit")
            stmt_db.eps = clean_values.get("eps")
            stmt_db.total_assets = clean_values.get("total_assets")
            stmt_db.total_liabilities = clean_values.get("total_liabilities")
            stmt_db.shareholders_equity = clean_values.get("shareholders_equity")
            stmt_db.operating_cash_flow = clean_values.get("operating_cash_flow")
            stmt_db.free_cash_flow = clean_values.get("free_cash_flow")
            stmt_db.capex = clean_values.get("capex")
            stmt_db.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            stmt_db = FinancialStatement(
                period_id=period.id,
                company_id=company_id,
                revenue=clean_values.get("revenue"),
                ebitda=clean_values.get("ebitda"),
                operating_income=clean_values.get("operating_income"),
                net_profit=clean_values.get("net_profit"),
                eps=clean_values.get("eps"),
                total_assets=clean_values.get("total_assets"),
                total_liabilities=clean_values.get("total_liabilities"),
                shareholders_equity=clean_values.get("shareholders_equity"),
                operating_cash_flow=clean_values.get("operating_cash_flow"),
                free_cash_flow=clean_values.get("free_cash_flow"),
                capex=clean_values.get("capex"),
            )
            self.db.add(stmt_db)

        await self.db.flush()

        # ── Step 6: Persist per-field evidence ───────────────────────────────
        logger.info("Step 6: Persisting per-field financial evidence.")
        
        # Clear old evidence first to avoid duplication on re-run
        from sqlalchemy import delete
        await self.db.execute(delete(FinancialEvidence).where(FinancialEvidence.statement_id == stmt_db.id))
        
        for field, chunk in chunk_source_map.items():
            if chunk is not None:
                ev_db = FinancialEvidence(
                    statement_id=stmt_db.id,
                    financial_field=field,
                    extracted_value=clean_values.get(field),
                    document_title=chunk.document_title,
                    page_number=chunk.page_number or 0,
                    section_title=chunk.section_title,
                    chunk_text=chunk.chunk_text,
                    similarity_score=float(chunk.similarity_score),
                )
                self.db.add(ev_db)
                field_evidence_list.append(FinancialFieldEvidence(
                    financial_field=field,
                    extracted_value=clean_values.get(field),
                    missing_reason=missing_reasons.get(field, {}).value if field in missing_reasons else None,
                    document_title=chunk.document_title,
                    page_number=chunk.page_number or 0,
                    section_title=chunk.section_title,
                    chunk_text=chunk.chunk_text,
                    similarity_score=float(chunk.similarity_score),
                ))

        # Add evidence for fields with missing_reason but no chunk
        for field, reason in missing_reasons.items():
            if chunk_source_map.get(field) is None:
                field_evidence_list.append(FinancialFieldEvidence(
                    financial_field=field,
                    extracted_value=None,
                    missing_reason=reason.value if hasattr(reason, 'value') else str(reason),
                    document_title="N/A",
                    page_number=0,
                    section_title=None,
                    chunk_text="",
                    similarity_score=0.0,
                ))

        # ── Step 7: Build FinancialStatementData for calculator ───────────────
        latest_stmt_data = FinancialStatementData(
            revenue=clean_values.get("revenue"),
            ebitda=clean_values.get("ebitda"),
            operating_income=clean_values.get("operating_income"),
            net_profit=clean_values.get("net_profit"),
            eps=clean_values.get("eps"),
            total_assets=clean_values.get("total_assets"),
            total_liabilities=clean_values.get("total_liabilities"),
            shareholders_equity=clean_values.get("shareholders_equity"),
            operating_cash_flow=clean_values.get("operating_cash_flow"),
            free_cash_flow=clean_values.get("free_cash_flow"),
            capex=clean_values.get("capex"),
        )

        # ── Step 8: Fetch previous period for YoY calculations ────────────────
        logger.info("Step 8: Fetching previous period for YoY metrics.")
        historical = await self.repository.get_statements_by_company(company_id, limit=2)
        prev_stmt_data = None
        if len(historical) >= 2:
            prev_db = historical[1]
            prev_stmt_data = FinancialStatementData(
                revenue=float(prev_db.revenue) if prev_db.revenue else None,
                eps=float(prev_db.eps) if prev_db.eps else None,
            )

        # ── Step 9: Calculate metrics ─────────────────────────────────────────
        logger.info("Step 9: Calculating financial metrics.")
        metrics_data, provenance_list = MetricCalculator.calculate_all(latest_stmt_data, prev_stmt_data)

        # Upsert FinancialMetric
        metric_q = select(FinancialMetric).where(
            FinancialMetric.statement_id == stmt_db.id,
            FinancialMetric.company_id == company_id
        )
        res_metric = await self.db.execute(metric_q)
        metric_db = res_metric.scalars().first()

        if metric_db:
            metric_db.revenue_growth_yoy = metrics_data.revenue_growth_yoy
            metric_db.ebitda_margin = metrics_data.ebitda_margin
            metric_db.net_profit_margin = metrics_data.net_profit_margin
            metric_db.roe = metrics_data.roe
            metric_db.roce = metrics_data.roce
            metric_db.debt_to_equity = metrics_data.debt_to_equity
            metric_db.current_ratio = metrics_data.current_ratio
            metric_db.free_cash_flow_yield = metrics_data.free_cash_flow_yield
            metric_db.eps_growth = metrics_data.eps_growth
            metric_db.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            metric_db = FinancialMetric(
                statement_id=stmt_db.id,
                company_id=company_id,
                revenue_growth_yoy=metrics_data.revenue_growth_yoy,
                ebitda_margin=metrics_data.ebitda_margin,
                net_profit_margin=metrics_data.net_profit_margin,
                roe=metrics_data.roe,
                roce=metrics_data.roce,
                debt_to_equity=metrics_data.debt_to_equity,
                current_ratio=metrics_data.current_ratio,
                free_cash_flow_yield=metrics_data.free_cash_flow_yield,
                eps_growth=metrics_data.eps_growth,
            )
            self.db.add(metric_db)

        await self.db.flush()

        # Clear old provenance to avoid duplication on re-run
        await self.db.execute(delete(FinancialMetricProvenance).where(FinancialMetricProvenance.metric_id == metric_db.id))

        for prov in provenance_list:
            prov_db = FinancialMetricProvenance(
                metric_id=metric_db.id,
                metric_name=prov.metric_name,
                formula=prov.formula,
                input_fields=prov.input_fields,
            )
            self.db.add(prov_db)

        await self.db.commit()

        # ── Step 10: Trend analysis ───────────────────────────────────────────
        logger.info("Step 10: Running trend analysis.")
        trend_analysis = await self.trend_analyzer.analyze(company_id=company_id)

        # ── Step 11: Build financial summary ──────────────────────────────────
        revenue_str = f"${latest_stmt_data.revenue:,.0f}" if latest_stmt_data.revenue else "N/A"
        net_profit_str = f"${latest_stmt_data.net_profit:,.0f}" if latest_stmt_data.net_profit else "N/A"
        margin_str = f"{metrics_data.net_profit_margin:.1f}%" if metrics_data.net_profit_margin else "N/A"

        financial_summary = (
            f"{company.company_name} reported revenue of {revenue_str} and net profit of {net_profit_str} "
            f"for fiscal year {resolved_fiscal_year}. Net profit margin: {margin_str}. "
            f"{'YoY revenue growth: {:.1f}%.'.format(metrics_data.revenue_growth_yoy) if metrics_data.revenue_growth_yoy else ''} "
            f"Data populated via {source_type.upper()} pipeline."
        ).strip()

        duration = time.perf_counter() - start_time
        logger.bind(
            company_id=str(company_id),
            duration_seconds=duration,
            fields_extracted=len([v for v in clean_values.values() if v is not None]),
            metrics_calculated=len(provenance_list),
        ).info("FinancialIntelligenceService.analyze completed.")

        response = FinancialAnalyzeResponse(
            company_id=company_id,
            company_name=company.company_name,
            fiscal_year=resolved_fiscal_year,
            period_type=resolved_period_type.value,
            currency="USD" if source_type == "yfinance" else "INR",
            financial_summary=financial_summary,
            latest_statement=latest_stmt_data,
            calculated_metrics=metrics_data,
            trend_analysis=trend_analysis,
            metric_provenance=provenance_list,
            financial_evidence=field_evidence_list,
            reporting_status=reporting_status,
        )
        
        await cache.set(cache_key, response.model_dump(), ttl=86400) # 24h
        return response

    async def _fetch_from_yfinance_fallback(
        self, ticker_symbol: str, exchange: str, year: int
    ) -> Dict[str, Optional[float]]:
        """
        Fetch historical financials from Yahoo Finance for a specific year.
        Returns a dict mapping the standard field names to normalized float values.
        """
        from app.services.market_data import _resolve_ticker
        import yfinance as yf
        import pandas as pd

        yf_ticker = _resolve_ticker(ticker_symbol, exchange)
        logger.info(f"FinancialIntelligence yfinance fallback triggered for {yf_ticker}, year {year}")
        
        try:
            loop = asyncio.get_event_loop()
            # yfinance >= 1.5.1 uses curl_cffi Chrome impersonation by default;
            # do NOT pass session= as it breaks financial-statement fetches.
            ticker = await loop.run_in_executor(None, lambda: yf.Ticker(yf_ticker))
            
            financials = await loop.run_in_executor(None, lambda: ticker.financials)
            balance_sheet = await loop.run_in_executor(None, lambda: ticker.balance_sheet)
            cashflow = await loop.run_in_executor(None, lambda: ticker.cashflow)

            def extract_val(df, row_names):
                if df is None or df.empty:
                    return None
                if isinstance(row_names, str):
                    row_names = [row_names]
                    
                matched_row = None
                for name in row_names:
                    if name in df.index:
                        matched_row = name
                        break
                
                if not matched_row:
                    return None

                for col in df.columns:
                    if str(year) in str(col):
                        val = df.loc[matched_row, col]
                        if pd.notna(val):
                            if hasattr(val, "iloc"):
                                return float(val.iloc[0])
                            return float(val)
                return None

            return {
                "revenue": extract_val(financials, ["Total Revenue", "Operating Revenue"]),
                "ebitda": extract_val(financials, ["EBITDA", "Normalized EBITDA"]),
                "operating_income": extract_val(financials, ["Operating Income", "Operating Income As Reported"]),
                "net_profit": extract_val(financials, ["Net Income", "Net Income Common Stockholders"]),
                "eps": extract_val(financials, ["Basic EPS", "Diluted EPS"]),
                "total_assets": extract_val(balance_sheet, ["Total Assets"]),
                "total_liabilities": extract_val(balance_sheet, ["Total Liabilities Net Minority Interest", "Total Liabilities"]),
                "shareholders_equity": extract_val(balance_sheet, ["Stockholders Equity", "Common Stock Equity"]),
                "operating_cash_flow": extract_val(cashflow, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"]),
                "free_cash_flow": extract_val(cashflow, ["Free Cash Flow"]),
                "capex": extract_val(cashflow, ["Capital Expenditure", "Purchase of PPE"]),
            }
        except Exception as e:
            logger.error(f"yfinance financials fetch failed for {yf_ticker}: {e}")
            return {
                "revenue": None, "ebitda": None, "operating_income": None, "net_profit": None, "eps": None,
                "total_assets": None, "total_liabilities": None, "shareholders_equity": None,
                "operating_cash_flow": None, "free_cash_flow": None, "capex": None
            }
