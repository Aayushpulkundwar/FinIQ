import time
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from app.db.session import get_db
from app.schemas.retrieval import RetrievalRequest, RetrievalResponse
from app.services.retrieval import RetrievalService

router = APIRouter()


@router.post("/search", response_model=List[RetrievalResponse])
async def search_knowledge(
    payload: RetrievalRequest, db: AsyncSession = Depends(get_db)
) -> List[RetrievalResponse]:
    """
    Execute semantic similarity query across document chunks using pgvector.
    Supports optional filters (company_id, document_type, fiscal_year, page_number)
    and custom similarity thresholds.
    """
    start_time = time.perf_counter()
    service = RetrievalService(db)

    # Compile filters list for structured logs
    filters_applied = {
        "company_id": str(payload.company_id) if payload.company_id else None,
        "document_type": payload.document_type.value if payload.document_type else None,
        "fiscal_year": payload.fiscal_year,
        "page_number": payload.page_number,
        "minimum_similarity": payload.minimum_similarity,
    }

    try:
        results = await service.search(
            query=payload.query,
            top_k=payload.top_k,
            min_similarity=payload.minimum_similarity,
            company_id=payload.company_id,
            document_type=payload.document_type,
            fiscal_year=payload.fiscal_year,
            page_number=payload.page_number,
        )

        duration = time.perf_counter() - start_time
        num_results = len(results)

        # Average similarity calculation
        avg_score = (
            sum(r.similarity_score for r in results) / num_results
            if num_results > 0
            else 0.0
        )

        # Structured log mapping
        logger.bind(
            query=payload.query,
            top_k=payload.top_k,
            filters=filters_applied,
            duration_seconds=duration,
            results_count=num_results,
            average_similarity=avg_score,
        ).info("Knowledge retrieval search query completed.")

        return results

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error during knowledge retrieval search: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while performing search: {e}",
        )
