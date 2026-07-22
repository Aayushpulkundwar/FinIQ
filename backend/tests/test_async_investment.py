import pytest
import uuid
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@patch("app.api.v1.routers.investment.run_investment_analysis_task")
def test_post_analyze_investment_success(mock_task):
    """Test enqueuing an investment analysis task successfully."""
    # Mock Celery delay result
    mock_result = MagicMock()
    mock_result.id = "test-task-123"
    mock_result.status = "PENDING"
    mock_task.delay.return_value = mock_result

    payload = {
        "company_id": str(uuid.uuid4()),
        "fiscal_year": 2026
    }
    
    response = client.post("/api/v1/investment/analyze", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert data["task_id"] == "test-task-123"
    assert data["status"] == "PENDING"
    mock_task.delay.assert_called_once_with(payload["company_id"], 2026)


@patch("app.api.v1.routers.investment.AsyncResult")
def test_get_task_status_progress(mock_async_result):
    """Test querying a task that is currently in PROGRESS."""
    mock_res = MagicMock()
    mock_res.state = "PROGRESS"
    mock_res.info = {"message": "Generating institutional research report..."}
    mock_async_result.return_value = mock_res

    response = client.get("/api/v1/investment/tasks/test-task-123")
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == "test-task-123"
    assert data["status"] == "PROGRESS"
    assert data["message"] == "Generating institutional research report..."


@patch("app.api.v1.routers.investment.AsyncResult")
def test_get_task_status_success(mock_async_result):
    """Test querying a task that has finished successfully."""
    mock_res = MagicMock()
    mock_res.state = "SUCCESS"
    mock_res.result = {
        "company_id": str(uuid.uuid4()),
        "company_name": "TVS Supply Chain Solutions Ltd",
        "valuation_summary": {
            "wacc_details": {
                "cost_of_equity": 0.10,
                "cost_of_debt": 0.05,
                "equity_weight": 0.6,
                "debt_weight": 0.4,
                "wacc": 0.08
            },
            "dcf_details": {
                "baseline_fcf": 1000.0,
                "fcf_growth_rate": 0.05,
                "projected_fcfs": [1050.0, 1102.5, 1157.6, 1215.5, 1276.3],
                "terminal_growth_rate": 0.02,
                "terminal_value": 22100.0,
                "enterprise_value": 18000.0,
                "equity_value": 16000.0,
                "shares_outstanding": 100.0,
                "intrinsic_share_price": 160.0
            },
            "sensitivity_grid": [],
            "confidence_score": 0.9,
            "valuation_flags": []
        },
        "intrinsic_value": 160.0,
        "sensitivity_analysis": [],
        "research_report": "# INVESTMENT RESEARCH REPORT: TVS Supply Chain Solutions Ltd\nExecutive Summary..."
    }
    mock_async_result.return_value = mock_res

    response = client.get("/api/v1/investment/tasks/test-task-123")
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == "test-task-123"
    assert data["status"] == "SUCCESS"
    assert data["result"]["company_name"] == "TVS Supply Chain Solutions Ltd"
    assert data["result"]["intrinsic_value"] == 160.0


@patch("app.api.v1.routers.investment.AsyncResult")
def test_get_task_status_failure(mock_async_result):
    """Test querying a task that has failed."""
    mock_res = MagicMock()
    mock_res.state = "FAILURE"
    mock_res.result = "LLMUnavailableException: OpenRouter call timed out after 120s"
    mock_async_result.return_value = mock_res

    response = client.get("/api/v1/investment/tasks/test-task-123")
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == "test-task-123"
    assert data["status"] == "FAILURE"
    assert data["error"] == "LLMUnavailableException: OpenRouter call timed out after 120s"
