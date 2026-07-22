import time
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from celery.result import AsyncResult

from app.db.session import get_db
from app.schemas.investment import (
    InvestmentAnalyzeRequest,
    InvestmentAnalyzeResponse,
    InvestmentTaskEnqueueResponse,
    InvestmentTaskStatusResponse,
)
from app.core.celery_app import celery_app
from app.services.tasks import run_investment_analysis_task

router = APIRouter()


@router.post("/analyze", response_model=InvestmentTaskEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
async def analyze_investment(
    payload: InvestmentAnalyzeRequest,
    db: AsyncSession = Depends(get_db)
) -> InvestmentTaskEnqueueResponse:
    """
    Coordinates Valuation and Investment Research report generation for a company asynchronously.
    Enqueues a Celery background task and returns immediately with a task_id.
    """
    logger.bind(
        company_id=str(payload.company_id),
        fiscal_year=payload.fiscal_year
    ).info("POST /api/v1/investment/analyze invoked. Enqueuing task...")

    try:
        # Enqueue background analysis task
        task = run_investment_analysis_task.delay(
            str(payload.company_id),
            payload.fiscal_year
        )
        
        return InvestmentTaskEnqueueResponse(
            task_id=task.id,
            status=task.status
        )
    except Exception as e:
        logger.error(f"Failed to enqueue investment analysis task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enqueue analysis task: {e}"
        )


@router.get("/tasks/{task_id}", response_model=InvestmentTaskStatusResponse)
async def get_task_status(task_id: str) -> InvestmentTaskStatusResponse:
    """
    Query the status of an enqueued investment analysis Celery task.
    """
    res = AsyncResult(task_id, app=celery_app)
    state = res.state

    if state == "PROGRESS":
        # Celery stores progress metadata in res.info
        message = None
        if isinstance(res.info, dict):
            message = res.info.get("message")
        return InvestmentTaskStatusResponse(
            task_id=task_id,
            status="PROGRESS",
            message=message or "Processing task..."
        )
    elif state == "SUCCESS":
        return InvestmentTaskStatusResponse(
            task_id=task_id,
            status="SUCCESS",
            result=res.result
        )
    elif state == "FAILURE":
        return InvestmentTaskStatusResponse(
            task_id=task_id,
            status="FAILURE",
            error=str(res.result)
        )
    else:
        # PENDING, STARTED, RETRY, etc.
        return InvestmentTaskStatusResponse(
            task_id=task_id,
            status=state
        )

