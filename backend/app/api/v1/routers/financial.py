import time
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from app.db.session import get_db
from app.schemas import Msg
from app.schemas.financial import FinancialAnalyzeRequest, FinancialAnalyzeResponse
from app.services.financial_intelligence import FinancialIntelligenceService

router = APIRouter()


@router.post("/analyze", response_model=FinancialAnalyzeResponse)
async def analyze_financial(
    payload: FinancialAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
) -> FinancialAnalyzeResponse:
    """
    Analyzes financial statements for a company.

    Execution flow:
    1. FinancialExtractor retrieves relevant document chunks using the RAG pipeline.
    2. FinancialParser extracts structured financial values via regex patterns.
    3. FinancialNormalizer handles unit and currency conversions.
    4. FinancialValidator validates values and classifies missing fields.
    5. Data is persisted to FinancialStatement, FinancialEvidence, FinancialMetric tables.
    6. MetricCalculator computes 9 financial ratios with full provenance.
    7. TrendAnalyzer provides multi-period historical trend classification.
    8. Returns FinancialAnalyzeResponse with full evidence and metric provenance.
    """
    start_time = time.perf_counter()
    logger.bind(
        company_id=str(payload.company_id),
        fiscal_year=payload.fiscal_year,
        period_type=payload.period_type,
    ).info("POST /api/v1/financial/analyze invoked.")

    try:
        service = FinancialIntelligenceService(db)
        result = await service.analyze(
            company_id=payload.company_id,
            fiscal_year=payload.fiscal_year,
            period_type=payload.period_type,
        )

        duration = time.perf_counter() - start_time
        logger.bind(
            company_name=result.company_name,
            fiscal_year=result.fiscal_year,
            metrics_calculated=len(result.metric_provenance),
            evidence_fields=len(result.financial_evidence),
            duration_seconds=duration,
        ).info("Financial analysis completed successfully.")

        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Financial analysis pipeline failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Financial analysis failed: {e}"
        )
