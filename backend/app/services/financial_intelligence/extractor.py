from typing import List, Dict, Any, Optional
from uuid import UUID
from loguru import logger
from app.services.retrieval import RetrievalService
from app.schemas.retrieval import RetrievalResponse

# Financial keyword groups for targeted retrieval
FINANCIAL_QUERY_GROUPS = [
    ("income_statement", "revenue net profit operating income EBITDA earnings per share"),
    ("balance_sheet", "total assets total liabilities shareholders equity"),
    ("cash_flow", "operating cash flow free cash flow capital expenditure CAPEX"),
]


class FinancialExtractor:
    """
    Retrieves financial-related document chunks from the existing RAG pipeline.
    Does NOT parse any numerical values — pure delegation to RetrievalService.
    """
    def __init__(self, retrieval_service: RetrievalService):
        self.retrieval_service = retrieval_service

    async def extract_chunks(
        self,
        company_id: UUID,
        fiscal_year: Optional[int] = None,
        top_k_per_group: int = 5
    ) -> Dict[str, List[RetrievalResponse]]:
        """
        Issues targeted retrieval queries per financial keyword group.
        Returns dict mapping group_name → List[RetrievalResponse].
        """
        results: Dict[str, List[RetrievalResponse]] = {}

        for group_name, query in FINANCIAL_QUERY_GROUPS:
            logger.bind(company_id=str(company_id), group=group_name, year=fiscal_year).info(
                "Extracting financial chunks for keyword group."
            )
            chunks = await self.retrieval_service.search(
                query=query,
                top_k=top_k_per_group,
                company_id=company_id,
                fiscal_year=fiscal_year
            )
            results[group_name] = chunks
            logger.bind(group=group_name, count=len(chunks)).debug("Chunks retrieved.")

        return results
