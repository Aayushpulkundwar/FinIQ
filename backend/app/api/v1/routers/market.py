import time
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.db.session import get_db
from app.schemas.market import (
    MarketAnalyzeRequest, MarketAnalyzeResponse,
    NewsIngestionRequest, NewsIngestionResponse
)
from app.services.market_intelligence import MarketIntelligenceService
from app.services.news_intelligence import NewsIntelligenceService

router = APIRouter()


@router.post("/analyze", response_model=MarketAnalyzeResponse)
async def analyze_market(
    payload: MarketAnalyzeRequest,
    db: AsyncSession = Depends(get_db)
) -> MarketAnalyzeResponse:
    """
    Retrieves recent news articles, computes sentiment distribution, maps industry/company mentions,
    correlates with event intelligence, and generates a structured AI market report.
    """
    start_time = time.perf_counter()
    logger.info("POST /api/v1/market/analyze invoked.")

    try:
        market_service = MarketIntelligenceService(db)
        analysis = await market_service.analyze(
            company_id=payload.company_id,
            industry=payload.industry,
            date_from=payload.date_from,
            date_to=payload.date_to,
            limit=payload.limit
        )

        duration = time.perf_counter() - start_time
        logger.bind(duration_seconds=duration).info("Market analysis completed successfully.")
        return analysis

    except Exception as e:
        logger.error(f"Market analysis pipeline failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Market analysis failed: {str(e)}"
        )


@router.post("/ingest", response_model=NewsIngestionResponse)
async def ingest_news(
    payload: NewsIngestionRequest,
    db: AsyncSession = Depends(get_db)
) -> NewsIngestionResponse:
    """
    Ingests a news article payload, classifies its category/sentiment, extracts mentioned tickers
    and industry terms, performs deduplication checking, and persists the data.
    """
    logger.bind(title=payload.title).info("POST /api/v1/market/ingest invoked.")

    try:
        news_service = NewsIntelligenceService(db)
        response = await news_service.ingest(payload)
        return response

    except Exception as e:
        logger.error(f"News article ingestion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"News ingestion failed: {str(e)}"
        )
