from typing import Optional, List, Dict, Any
from uuid import UUID
from langchain_core.tools import StructuredTool
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.retrieval import RetrievalService, is_overview_query
from app.services.company import CompanyService
from app.services.document import DocumentService
from app.services.event_intelligence import EventIntelligenceService
from app.services.financial_intelligence import FinancialIntelligenceService
from app.services.valuation import ValuationService
from app.services.research_report import ResearchReportService
from app.services.market_intelligence import MarketIntelligenceService
from app.models.document import DocumentType


def create_tools(db: AsyncSession) -> Dict[str, StructuredTool]:
    """
    Factory creating LangChain/LangGraph tool adapters around backend services,
    binding the active database transaction session.
    """
    retrieval_service = RetrievalService(db)
    company_service = CompanyService(db)
    document_service = DocumentService(db)
    event_intelligence_service = EventIntelligenceService(db)
    financial_intelligence_service = FinancialIntelligenceService(db)
    valuation_service = ValuationService(db)
    research_report_service = ResearchReportService(db)
    market_intelligence_service = MarketIntelligenceService(db)

    async def search_knowledge(
        query: str,
        top_k: int = 5,
        minimum_similarity: Optional[float] = None,
        company_id: Optional[str] = None,
        document_type: Optional[str] = None,
        fiscal_year: Optional[int] = None,
        page_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Executes semantic search across document chunks using pgvector.
        Optionally filters by company_id, document_type, fiscal_year, page_number,
        and minimum similarity score.
        """
        c_id = None
        if company_id:
            try:
                c_id = UUID(company_id)
            except ValueError:
                # Treat company_id as ticker symbol or name
                company = await company_service.repository.get_by_ticker(company_id.upper())
                if company:
                    c_id = company.id
                else:
                    # Search by name
                    companies = await company_service.repository.get_multi()
                    for c in companies:
                        if company_id.lower() in c.company_name.lower() or c.company_name.lower() in company_id.lower():
                            c_id = c.id
                            break
                            
        if not c_id:
            # NOTE: Known Limitation - Coreference Resolution
            # If the user query is a follow-up (e.g. "what about its debt-to-equity"),
            # this semantic search does not currently resolve pronouns like "its" or references
            # to previous conversation history. A full coreference resolution layer (using LLM
            # or heuristics) would be needed to map context history to company identifiers.
            # Look up if query mentions any known company name or ticker
            companies = await company_service.repository.get_multi()
            for c in companies:
                if c.ticker_symbol.lower() in query.lower() or c.company_name.lower() in query.lower():
                    c_id = c.id
                    break

        doc_type = DocumentType(document_type) if document_type else None

        # For overview/summary queries, retrieve more candidates so the
        # reranker has enough business-description chunks to surface before
        # the financial/governance chunks crowd the top-k window.
        effective_top_k = top_k
        if is_overview_query(query):
            effective_top_k = max(top_k, 8)

        results = await retrieval_service.search(
            query=query,
            top_k=effective_top_k,
            min_similarity=minimum_similarity,
            company_id=c_id,
            document_type=doc_type,
            fiscal_year=fiscal_year,
            page_number=page_number,
        )
        return [r.model_dump() for r in results]

    async def get_company_by_ticker(ticker_symbol: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves corporate record profile metadata for a specific ticker symbol.
        """
        company = await company_service.repository.get_by_ticker(ticker_symbol.upper())
        if not company:
            return None
        return {
            "id": str(company.id),
            "company_name": company.company_name,
            "ticker_symbol": company.ticker_symbol,
            "exchange": company.exchange,
            "sector": company.sector,
            "industry": company.industry,
            "isin": company.isin,
            "website": company.website,
        }

    async def list_companies() -> List[Dict[str, Any]]:
        """
        Lists all registered corporate entities currently stored.
        """
        companies = await company_service.list_companies(skip=0, limit=100)
        return [
            {
                "id": str(c.id),
                "company_name": c.company_name,
                "ticker_symbol": c.ticker_symbol,
                "exchange": c.exchange,
            }
            for c in companies
        ]

    async def get_document_metadata(document_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves registration and processing status logs for a specific document ID.
        """
        try:
            doc = await document_service.get_document(UUID(document_id))
            return {
                "id": str(doc.id),
                "company_id": str(doc.company_id),
                "title": doc.title,
                "document_type": doc.document_type.value,
                "fiscal_year": doc.fiscal_year,
                "quarter": doc.quarter,
                "file_name": doc.file_name,
                "file_size": doc.file_size,
                "upload_status": doc.upload_status.value,
                "processing_status": doc.processing_status.value,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
            }
        except KeyError:
            return None

    async def list_documents(company_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieves metadata headers for ingested files, optionally filtered by company ID.
        """
        if company_id:
            c_uuid = UUID(company_id)
            from sqlalchemy import select
            stmt = select(document_service.repository.model).where(
                document_service.repository.model.company_id == c_uuid
            )
            result = await document_service.repository.db.execute(stmt)
            documents = result.scalars().all()
        else:
            documents = await document_service.list_documents(skip=0, limit=100)

        return [
            {
                "id": str(d.id),
                "company_id": str(d.company_id),
                "title": d.title,
                "document_type": d.document_type.value,
                "fiscal_year": d.fiscal_year,
                "quarter": d.quarter,
                "processing_status": d.processing_status.value,
            }
            for d in documents
        ]

    async def analyze_event_intelligence(title: str, description: str) -> Dict[str, Any]:
        """
        Analyzes a corporate or market event to classify its type and severity, identify affected
        industries, match potentially impacted companies, determine impact direction, and retrieve
        supporting document chunk evidence. Use for event-related, regulatory, macroeconomic,
        geopolitical, or industry-disruption queries.
        """
        result = await event_intelligence_service.analyze(
            title=title,
            description=description
        )
        return result.model_dump()

    async def analyze_financial_intelligence(
        company_id: str,
        fiscal_year: Optional[int] = None,
        period_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Extracts financial statement data from company filings, calculates key financial ratios
        and metrics (EBITDA margin, ROE, ROCE, Debt/Equity, revenue growth YoY, etc.),
        performs historical trend analysis, and returns per-field evidence citations.
        Use for financial analysis queries: revenue, earnings, margins, balance sheet, cash flow.
        """
        result = await financial_intelligence_service.analyze(
            company_id=UUID(company_id),
            fiscal_year=fiscal_year,
            period_type=period_type,
        )
        return result.model_dump()



    async def calculate_company_valuation(
        company_id: str,
        fiscal_year: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Calculates WACC, projects 5-year FCF, computes terminal/enterprise/equity value,
        and generates sensitivity grid and confidence scores. Use for stock/company valuation,
        DCF, WACC, intrinsic share price estimation, and price sensitivity queries.
        """
        result = await valuation_service.calculate_valuation(
            company_id=UUID(company_id),
            fiscal_year=fiscal_year,
        )
        return result.model_dump()

    async def generate_research_report(
        company_id: str,
        fiscal_year: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generates a comprehensive, institutional-quality investment research report for a company,
        aggregating financial performance, key ratios, valuations, DCF, and evidence citations.
        Use for research report or comprehensive company/investment analysis queries.
        """
        report_md = await research_report_service.generate_report(
            company_id=UUID(company_id),
            fiscal_year=fiscal_year,
        )
        return {"report": report_md}

    async def analyze_market_intelligence(
        company_id: Optional[str] = None,
        industry: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Aggregates recent financial news, computes sentiment, identifies impacted companies
        and industries, correlates with events, and generates a market intelligence summary.
        Use for market news, headlines, market update, sentiment, and market summary queries.
        """
        result = await market_intelligence_service.analyze(
            company_id=UUID(company_id) if company_id else None,
            industry=industry,
            limit=limit,
        )
        return result.model_dump()

    return {
        "search_knowledge": StructuredTool.from_function(
            coroutine=search_knowledge,
            name="search_knowledge",
            description="Executes semantic search across document chunks using pgvector.",
        ),
        "get_company_by_ticker": StructuredTool.from_function(
            coroutine=get_company_by_ticker,
            name="get_company_by_ticker",
            description="Retrieves corporate record profile metadata for a specific ticker symbol.",
        ),
        "list_companies": StructuredTool.from_function(
            coroutine=list_companies,
            name="list_companies",
            description="Lists all registered corporate entities currently stored.",
        ),
        "get_document_metadata": StructuredTool.from_function(
            coroutine=get_document_metadata,
            name="get_document_metadata",
            description="Retrieves registration and processing status logs for a specific document ID.",
        ),
        "list_documents": StructuredTool.from_function(
            coroutine=list_documents,
            name="list_documents",
            description="Retrieves metadata headers for ingested files, optionally filtered by company ID.",
        ),
        "analyze_event_intelligence": StructuredTool.from_function(
            coroutine=analyze_event_intelligence,
            name="analyze_event_intelligence",
            description=(
                "Analyzes a corporate or market event: classifies type and severity, identifies affected "
                "industries, matches impacted companies, determines positive/negative/neutral impact, "
                "and retrieves supporting document evidence. Use for any event-related, regulatory, "
                "macroeconomic, geopolitical, or industry-disruption queries."
            ),
        ),
        "analyze_financial_intelligence": StructuredTool.from_function(
            coroutine=analyze_financial_intelligence,
            name="analyze_financial_intelligence",
            description=(
                "Extracts financial statement data (revenue, EBITDA, net profit, EPS, assets, liabilities, "
                "cash flow) from company filings, calculates key financial ratios (margins, ROE, ROCE, "
                "debt-to-equity), performs YoY trend analysis, and returns per-field evidence citations. "
                "Use for any financial analysis, earnings, balance sheet, or ratio queries."
            ),
        ),
        "calculate_company_valuation": StructuredTool.from_function(
            coroutine=calculate_company_valuation,
            name="calculate_company_valuation",
            description=(
                "Calculates WACC, projects 5-year FCF, computes terminal/enterprise/equity value, "
                "and generates sensitivity grid and confidence scores. Use for stock/company valuation, "
                "DCF, WACC, intrinsic share price estimation, and price sensitivity queries."
            ),
        ),
        "generate_research_report": StructuredTool.from_function(
            coroutine=generate_research_report,
            name="generate_research_report",
            description=(
                "Generates a comprehensive, institutional-quality investment research report for a company, "
                "aggregating financial performance, key ratios, valuations, DCF, and evidence citations. "
                "Use for research report or comprehensive company/investment analysis queries."
            ),
        ),
        "analyze_market_intelligence": StructuredTool.from_function(
            coroutine=analyze_market_intelligence,
            name="analyze_market_intelligence",
            description=(
                "Aggregates and analyzes recent financial news, computes sentiment breakdown, identifies "
                "impacted companies and industries, and generates structured market intelligence. "
                "Use for market news, headlines, market update, market sentiment, and market summary queries."
            ),
        ),
    }

