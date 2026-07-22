import pytest
from fastapi.testclient import TestClient


def test_root(client: TestClient) -> None:
    """Test standard root welcome route."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "FinsightAI" in data["message"]
    assert "docs" in data


def test_health_check(client: TestClient) -> None:
    """Test health check route."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "services" in data
    assert "database" in data["services"]
    assert "redis" in data["services"]

