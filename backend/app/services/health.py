from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from loguru import logger
from app.core.config import settings
from app.schemas.health import HealthCheckResponse, ServicesHealth


class HealthService:
    """
    Service responsible for verifying connection status of external dependencies.
    Decoupled from FastAPI HTTP routes.
    """
    @staticmethod
    async def check_health(db: AsyncSession) -> HealthCheckResponse:
        """
        Runs check queries on PostgreSQL and Redis dependencies.
        Validates connection status and returns connection reports.
        """
        db_connected = True
        redis_connected = True

        # 1. Verify PostgreSQL Database connection
        try:
            await db.execute(text("SELECT 1"))
        except Exception as e:
            logger.bind(service="database").error(
                f"PostgreSQL connection check failed: {e}"
            )
            db_connected = False

        # 2. Verify Redis connection (if configured)
        if settings.REDIS_HOST:
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
                logger.bind(service="redis").error(
                    f"Redis connection check failed: {e}"
                )
                redis_connected = False
        else:
            logger.warning("Redis is not configured. Skipping Redis health check.")
            redis_connected = False

        status = "healthy" if db_connected and redis_connected else "unhealthy"

        return HealthCheckResponse(
            status=status,
            version=settings.VERSION,
            environment=settings.ENVIRONMENT,
            services=ServicesHealth(
                database="connected" if db_connected else "disconnected",
                redis="connected" if redis_connected else "disconnected",
            ),
        )
