from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.db.session import get_db
from app.core.config import settings
from app.schemas import HealthCheck
from loguru import logger

router = APIRouter()


@router.get("", response_model=HealthCheck)
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthCheck:
    """
    Perform a health check verification on all underlying backing services.
    """
    db_status = "healthy"
    redis_status = "healthy"

    # Database connection test
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"

    # Redis connection test
    try:
        r = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            socket_timeout=1.0,
        )
        await r.ping()
        await r.close()
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        redis_status = "unhealthy"

    overall_status = (
        "healthy"
        if db_status == "healthy" and redis_status == "healthy"
        else "unhealthy"
    )

    return HealthCheck(
        status=overall_status,
        version="0.1.0",
        database=db_status,
        redis=redis_status,
    )
