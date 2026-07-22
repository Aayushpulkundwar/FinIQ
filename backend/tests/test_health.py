import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app


def test_health_check_healthy(client: TestClient):
    """Test health check endpoint when all backend systems are online."""
    with patch("app.services.health.HealthService.check_health") as mock_check:
        from app.schemas.health import HealthCheckResponse, ServicesHealth
        mock_check.return_value = HealthCheckResponse(
            status="healthy",
            version="0.1.0",
            environment="local",
            services=ServicesHealth(database="connected", redis="connected")
        )

        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["services"]["database"] == "connected"
        assert data["services"]["redis"] == "connected"


def test_health_check_database_offline(client: TestClient):
    """Test health check endpoint when PostgreSQL connection is down."""
    with patch("app.services.health.HealthService.check_health") as mock_check:
        from app.schemas.health import HealthCheckResponse, ServicesHealth
        mock_check.return_value = HealthCheckResponse(
            status="unhealthy",
            version="0.1.0",
            environment="local",
            services=ServicesHealth(database="disconnected", redis="connected")
        )

        response = client.get("/api/v1/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["services"]["database"] == "disconnected"
        assert data["services"]["redis"] == "connected"


def test_health_check_redis_offline(client: TestClient):
    """Test health check endpoint when Redis connection is down."""
    with patch("app.services.health.HealthService.check_health") as mock_check:
        from app.schemas.health import HealthCheckResponse, ServicesHealth
        mock_check.return_value = HealthCheckResponse(
            status="unhealthy",
            version="0.1.0",
            environment="local",
            services=ServicesHealth(database="connected", redis="disconnected")
        )

        response = client.get("/api/v1/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["services"]["database"] == "connected"
        assert data["services"]["redis"] == "disconnected"


@pytest.mark.asyncio
async def test_health_service_postgres_fail():
    """Verify HealthService handles Postgres failure gracefully and returns status mapping."""
    from app.services.health import HealthService

    db_mock = AsyncMock()
    db_mock.execute.side_effect = Exception("Postgres connection timeout")

    with patch("app.services.health.Redis") as MockRedis:
        mock_redis_instance = AsyncMock()
        MockRedis.return_value = mock_redis_instance

        result = await HealthService.check_health(db_mock)
        assert result.status == "unhealthy"
        assert result.services.database == "disconnected"
        assert result.services.redis == "connected"


@pytest.mark.asyncio
async def test_health_service_redis_fail():
    """Verify HealthService handles Redis failure gracefully and returns status mapping."""
    from app.services.health import HealthService

    db_mock = AsyncMock()
    db_mock.execute.return_value = AsyncMock()

    with patch("app.services.health.Redis") as MockRedis:
        mock_redis_instance = AsyncMock()
        mock_redis_instance.ping.side_effect = Exception("Redis network timeout")
        MockRedis.return_value = mock_redis_instance

        result = await HealthService.check_health(db_mock)
        assert result.status == "unhealthy"
        assert result.services.database == "connected"
        assert result.services.redis == "disconnected"
