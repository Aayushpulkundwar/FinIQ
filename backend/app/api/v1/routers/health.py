from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.health import HealthCheckResponse
from app.services.health import HealthService

router = APIRouter()


@router.get("", response_model=HealthCheckResponse)
async def health_check(
    response: Response, db: AsyncSession = Depends(get_db)
) -> HealthCheckResponse:
    """
    Perform a health check on the core dependencies of the application.
    Returns HTTP 200 if PostgreSQL and Redis are both healthy and connected,
    otherwise returns HTTP 503 Service Unavailable.
    """
    health = await HealthService.check_health(db)
    if health.status == "unhealthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return health
