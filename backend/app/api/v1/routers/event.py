import time
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from app.db.session import get_db
from app.schemas import Msg
from app.schemas.event import EventAnalyzeRequest, EventAnalyzeResponse
from app.services.event_intelligence import EventIntelligenceService
from app.services.response_generation import ResponseGenerationService

router = APIRouter()


@router.get("", response_model=Msg)
async def list_events() -> Msg:
    """Placeholder list events endpoint."""
    return Msg(msg="List events route placeholder")


@router.get("/{event_id}", response_model=Msg)
async def get_event(event_id: str) -> Msg:
    """Placeholder get event endpoint."""
    return Msg(msg=f"Get event {event_id} route placeholder")


@router.post("/analyze", response_model=EventAnalyzeResponse)
async def analyze_event(
    payload: EventAnalyzeRequest,
    db: AsyncSession = Depends(get_db)
) -> EventAnalyzeResponse:
    """
    Analyzes a corporate or market event to produce a structured event intelligence report.

    Execution flow:
    1. EventIntelligenceService classifies the event and maps direct/indirect affected industries.
    2. CompanyMatcher finds companies in affected industries with confidence scores.
    3. ImpactAnalyzer determines positive, negative, or neutral impact for each company.
    4. EvidenceRetriever retrieves supporting document evidence using the RAG pipeline.
    5. ResponseGenerationService generates the final grounded AI response from context.
    """
    start_time = time.perf_counter()
    logger.bind(title=payload.title).info("POST /api/v1/events/analyze invoked.")

    try:
        # Step 1: Run Event Intelligence analysis pipeline
        event_service = EventIntelligenceService(db)
        analysis = await event_service.analyze(
            title=payload.title,
            description=payload.description
        )

        duration = time.perf_counter() - start_time
        logger.bind(
            event_type=analysis.event_type,
            severity=analysis.severity,
            affected_industries=analysis.affected_industries,
            impacted_companies=len(analysis.potentially_impacted_companies),
            duration_seconds=duration
        ).info("Event analysis completed successfully.")

        return analysis

    except Exception as e:
        logger.error(f"Event analysis pipeline failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Event analysis failed: {e}"
        )
