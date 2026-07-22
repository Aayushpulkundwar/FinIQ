import time
import json
from typing import Optional, List, Dict, Any
from uuid import UUID
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.retrieval import RetrievalService
from app.services.response_generation import ResponseGenerationService
from app.services.financial_intelligence.service import FinancialIntelligenceService
from app.services.valuation import ValuationService
from app.services.company import CompanyService
from app.schemas.response_generation import AIResponse


class ResearchReportService:
    """
    ResearchReportService is responsible for generating institutional-quality investment
    research reports by aggregating data from the Retrieval, Financial, Event, and Valuation services.

    It coordinates data assembly and delegates final report rendering to ResponseGenerationService.
    Does NOT contain business logic or valuation calculations inside itself.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.company_service = CompanyService(db)
        self.retrieval_service = RetrievalService(db)
        self.financial_service = FinancialIntelligenceService(db)
        self.valuation_service = ValuationService(db)
        self.response_generator = ResponseGenerationService()

    async def generate_report(
        self,
        company_id: UUID,
        fiscal_year: Optional[int] = None,
    ) -> str:
        """
        Aggregates financial, event, and valuation data, compiles it into a structured
        context, and invokes the ResponseGenerationService to generate a polished markdown report.
        """
        logger.bind(company_id=str(company_id), fiscal_year=fiscal_year).info(
            "ResearchReportService: starting generation."
        )

        company = await self.company_service.repository.get(company_id)
        if not company:
            raise ValueError(f"Company with id={company_id} not found.")

        # 1. Fetch Financials & Trends
        start_time = time.perf_counter()
        fin_data = await self.financial_service.analyze(company_id, fiscal_year=fiscal_year)
        logger.info(f"ResearchReportService: Step 1 (Financial analysis) completed in {time.perf_counter() - start_time:.2f}s")

        # 2. Fetch Valuation
        start_time = time.perf_counter()
        val_data = await self.valuation_service.calculate_valuation(company_id, fiscal_year=fiscal_year)
        logger.info(f"ResearchReportService: Step 2 (Valuation calculation) completed in {time.perf_counter() - start_time:.2f}s")

        # 3. Retrieve relevant text chunks for additional overview/risks context
        start_time = time.perf_counter()
        text_chunks = await self.retrieval_service.search(
            query="business model overview competition risks industry opportunities",
            top_k=8,
            company_id=company_id
        )
        logger.info(f"ResearchReportService: Step 3 (Filing context RAG retrieval) completed in {time.perf_counter() - start_time:.2f}s")

        # Construct aggregate structural context
        company_dict = {
            "company_name": company.company_name,
            "ticker_symbol": company.ticker_symbol,
            "exchange": company.exchange,
            "sector": company.sector,
            "industry": company.industry,
        }

        # Build list of metadata and retrieved chunks for the ResponseGenerationService contract
        doc_metadata: List[Dict[str, Any]] = []
        retrieved_chunks: List[Dict[str, Any]] = []

        # Aggregate evidence from financial parser chunks
        for ev in fin_data.financial_evidence:
            if ev.chunk_text:
                retrieved_chunks.append({
                    "chunk_text": ev.chunk_text,
                    "document_title": ev.document_title,
                    "page_number": ev.page_number,
                    "section_title": ev.section_title,
                    "similarity_score": ev.similarity_score,
                })

        # Add general text chunks
        for chunk in text_chunks:
            retrieved_chunks.append({
                "chunk_text": chunk.chunk_text,
                "document_title": chunk.document_title,
                "page_number": chunk.page_number,
                "section_title": chunk.section_title,
                "similarity_score": float(chunk.similarity_score),
            })

        # Safeguard formatting values against None
        stmt = fin_data.latest_statement
        metrics = fin_data.calculated_metrics

        rev_val = stmt.revenue
        rev_str = f"${rev_val:,.2f}" if rev_val is not None else "N/A"

        np_val = stmt.net_profit
        np_str = f"${np_val:,.2f}" if np_val is not None else "N/A"

        rev_growth = metrics.revenue_growth_yoy
        rev_growth_val_str = f"{rev_growth}" if rev_growth is not None else "N/A"

        ebitda_margin = metrics.ebitda_margin
        ebitda_margin_val_str = f"{ebitda_margin}" if ebitda_margin is not None else "N/A"

        roe = metrics.roe
        roe_val_str = f"{roe}" if roe is not None else "N/A"

        debt_to_equity = metrics.debt_to_equity
        debt_to_equity_str = f"{debt_to_equity}" if debt_to_equity is not None else "N/A"

        intrinsic_price = val_data.dcf_details.intrinsic_share_price if val_data and val_data.dcf_details else None
        intrinsic_price_str = f"${intrinsic_price}" if intrinsic_price is not None else "N/A"

        wacc = val_data.wacc_details.wacc if val_data and val_data.wacc_details else None
        wacc_str = f"{wacc * 100:.2f}%" if wacc is not None else "N/A"

        terminal_growth = val_data.dcf_details.terminal_growth_rate if val_data and val_data.dcf_details else None
        terminal_growth_str = f"{terminal_growth * 100:.2f}%" if terminal_growth is not None else "N/A"

        confidence_score = val_data.confidence_score if val_data else None
        confidence_score_str = f"{confidence_score * 100:.0f}%" if confidence_score is not None else "N/A"

        # Formulate query explaining what to generate
        user_query = (
            f"Generate a comprehensive, institutional-quality investment research report for {company.company_name} ({company.ticker_symbol}). "
            f"Integrate these specific inputs:\n"
            f"- Financial Performance: Revenue {rev_str}, Net Profit {np_str} "
            f"with YoY Revenue Growth of {rev_growth_val_str}%\n"
            f"- Financial Ratios: EBITDA Margin {ebitda_margin_val_str}%, ROE {roe_val_str}%, Debt-to-Equity {debt_to_equity_str}\n"
            f"- DCF Valuation: Intrinsic Share Price of {intrinsic_price_str} calculated using WACC of {wacc_str}\n"
            f"- Sensitivity Analysis highlights: Base Case {intrinsic_price_str}\n"
            f"Format into standard sections: Executive Summary, Company Overview, Business Model, Industry Analysis, "
            f"Financial Performance, Financial Ratios, Event Intelligence Summary, Valuation Summary, Key Risks, "
            f"Opportunities, Investment Thesis, Conclusion, Supporting Evidence."
        )

        # Call response generator
        start_time = time.perf_counter()
        ai_resp: AIResponse = await self.response_generator.generate_response(
            user_query=user_query,
            company_details=company_dict,
            document_metadata=doc_metadata,
            retrieved_chunks=retrieved_chunks,
        )
        logger.info(f"ResearchReportService: Step 4 (LLM OpenRouter response generation) completed in {time.perf_counter() - start_time:.2f}s")

        if not ai_resp:
            from app.core.exceptions import LLMUnavailableException
            raise LLMUnavailableException("AI service failed to generate a response.")

        if ai_resp.error_message:
            from app.core.exceptions import LLMUnavailableException
            if ai_resp.error_type == "rate_limited":
                raise LLMUnavailableException(ai_resp.error_message, status_code=429)
            elif ai_resp.error_type == "json_parse_failure":
                logger.warning(
                    f"ResearchReportService: LLM output (provider={ai_resp.provider}) "
                    f"failed JSON parsing. Detail: {ai_resp.error_message}"
                )
                raise LLMUnavailableException("AI response could not be parsed as structured data, please retry.", status_code=503)
            else:
                raise LLMUnavailableException(ai_resp.error_message, status_code=503)

        # Structure report into polished markdown using fields from AIResponse
        insights = "\n".join([f"- {i}" for i in ai_resp.key_insights])
        evidence = "\n".join([f"- {e}" for e in ai_resp.supporting_evidence])
        risks = "\n".join([f"- {r}" for r in ai_resp.risks_limitations])
        sources = "\n".join([f"- {s}" for s in ai_resp.sources])

        report_md = (
            f"# INVESTMENT RESEARCH REPORT: {company.company_name} ({company.ticker_symbol.upper()})\n\n"
            f"## 1. Executive Summary\n"
            f"{ai_resp.executive_summary}\n\n"
            f"## 2. Company & Business Model Overview\n"
            f"Sector: {company.sector} | Industry: {company.industry}\n"
            f"Business model insights gathered from filings:\n{insights}\n\n"
            f"## 3. Financial Performance & Key Ratios\n"
            f"Latest reporting period reveals revenue of {rev_str} "
            f"and net profit of {np_str}.\n"
            f"- EBITDA Margin: {ebitda_margin_val_str}%\n"
            f"- Return on Equity (ROE): {roe_val_str}%\n"
            f"- Debt-to-Equity Ratio: {debt_to_equity_str}\n"
            f"- Growth YoY: {rev_growth_val_str}%\n\n"
            f"## 4. Valuation & DCF Analysis\n"
            f"Based on our Valuation Engine projection models, we calculate:\n"
            f"- **Estimated Intrinsic share price**: {intrinsic_price_str}\n"
            f"- **Discount rate (WACC)**: {wacc_str}\n"
            f"- **Terminal perpetuity growth rate**: {terminal_growth_str}\n"
            f"- **Valuation confidence score**: {confidence_score_str}\n\n"
            f"## 5. Investment Thesis, Opportunities, & Risks\n"
            f"### Opportunities:\n{insights}\n"
            f"### Key Risks:\n{risks}\n\n"
            f"## 6. Supporting Evidence & Sources\n"
            f"### Citations & Verified Statements:\n{evidence}\n"
            f"### Data Sources:\n{sources}\n"
        )

        logger.info("ResearchReportService: completed report generation.")
        return report_md
