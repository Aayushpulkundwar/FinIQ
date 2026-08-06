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
    Deduplicates active Celery tasks and serves 30-minute cached results from Redis.
    """
    from app.core.cache import cache
    from app.core.utils import normalize_fiscal_year

    company_id_str = str(payload.company_id)
    fiscal_year = normalize_fiscal_year(payload.fiscal_year)
    result_cache_key = f"investment_analysis:v1:{company_id_str}:{fiscal_year}"
    active_lock_key = f"investment_task_active:{company_id_str}:{fiscal_year}"

    logger.bind(
        company_id=company_id_str,
        fiscal_year=fiscal_year
    ).info("POST /api/v1/investment/analyze invoked.")

    try:
        # 1. Return cached result immediately if available
        cached_result = await cache.get(result_cache_key)
        if cached_result:
            logger.info(f"Returning cached investment analysis result for company {company_id_str}, FY {fiscal_year}")
            return InvestmentTaskEnqueueResponse(
                task_id=f"cached:{company_id_str}:{fiscal_year}",
                status="SUCCESS"
            )

        # 2. Re-use existing active Celery task if running in non-terminal state
        active_task_id = await cache.get(active_lock_key)
        if active_task_id:
            task_res = AsyncResult(active_task_id, app=celery_app)
            if task_res.state in ["PENDING", "STARTED", "PROGRESS"]:
                logger.info(f"Re-using active Celery task {active_task_id} for company {company_id_str}, FY {fiscal_year}")
                return InvestmentTaskEnqueueResponse(
                    task_id=active_task_id,
                    status=task_res.state
                )
            else:
                logger.warning(f"Active task lock {active_task_id} is in terminal state ({task_res.state}). Clearing stale lock.")
                await cache.delete(active_lock_key)

        # 3. Enqueue fresh Celery background task
        task = run_investment_analysis_task.delay(
            company_id_str,
            fiscal_year
        )
        
        # Set active task lock with 300s (5-minute) safety TTL
        await cache.set(active_lock_key, task.id, ttl=300)
        
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
    Query the status of an enqueued investment analysis Celery task or cached result.
    """
    from app.core.cache import cache
    from app.core.utils import normalize_fiscal_year

    if task_id.startswith("cached:"):
        parts = task_id.split(":")
        if len(parts) >= 3:
            co_id = parts[1]
            fy = normalize_fiscal_year(parts[2])
            cached_result = await cache.get(f"investment_analysis:v1:{co_id}:{fy}")
            if cached_result:
                return InvestmentTaskStatusResponse(
                    task_id=task_id,
                    status="SUCCESS",
                    result=cached_result
                )

    res = AsyncResult(task_id, app=celery_app)
    state = res.state

    if state == "PROGRESS":
        message = None
        if isinstance(res.info, dict):
            message = res.info.get("message")
        return InvestmentTaskStatusResponse(
            task_id=task_id,
            status="PROGRESS",
            message=message or "Processing task..."
        )
    elif state == "SUCCESS":
        if res.result and isinstance(res.result, dict):
            company_id = res.result.get("company_id")
            fy_raw = res.result.get("fiscal_year") or 2026
            fy = normalize_fiscal_year(fy_raw)
            if company_id:
                cache_key = f"investment_analysis:v1:{company_id}:{fy}"
                await cache.set(cache_key, res.result, ttl=1800)
                await cache.delete(f"investment_task_active:{company_id}:{fy}")
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
        return InvestmentTaskStatusResponse(
            task_id=task_id,
            status=state
        )

