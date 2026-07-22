import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

def test_diagnostic_endpoint(client: TestClient):
    """Verify that POST /api/v1/chat/diagnostic runs and returns status reports."""
    mock_db_result = MagicMock()
    mock_db_result.scalars.return_value.first.return_value = None  # Mock no company found to run quickly
    mock_db_result.scalar.return_value = 0

    with patch("app.api.v1.routers.chat.AsyncSession") as MockSession:
        response = client.post("/api/v1/chat/diagnostic")
        assert response.status_code == 200
        data = response.json()
        assert "database_inspection" in data
        assert "queries_executed" in data
        assert "overall_status" in data
        assert data["database_inspection"]["company_name"] == "Arvind Limited"
        assert data["database_inspection"]["status"] == "FAIL"  # Mock set it to FAIL because company is not found
