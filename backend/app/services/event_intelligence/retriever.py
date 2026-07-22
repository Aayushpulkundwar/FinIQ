from typing import List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.retrieval import RetrievalService
from app.schemas.event import Evidence


class EvidenceRetriever:
    """
    Reuses the existing RetrievalService to extract factual document chunks
    supporting the company's analyzed event impact profile.
    """
    def __init__(self, db: AsyncSession):
        self.retrieval_service = RetrievalService(db)

    async def retrieve_evidence(
        self,
        company_id: UUID,
        query: str,
        top_k: int = 2
    ) -> List[Evidence]:
        """
        Delegates search execution to RetrievalService, applying company scoping,
        and translates matching records to typed Evidence models.
        """
        # Execute query filtered by company_id using parent RAG service
        results = await self.retrieval_service.search(
            query=query,
            top_k=top_k,
            company_id=company_id
        )

        evidence_list = []
        for r in results:
            evidence_list.append(
                Evidence(
                    document_title=r.document_title,
                    page_number=r.page_number,
                    section_title=r.section_title,
                    chunk_text=r.chunk_text,
                    similarity_score=r.similarity_score
                )
            )

        return evidence_list
