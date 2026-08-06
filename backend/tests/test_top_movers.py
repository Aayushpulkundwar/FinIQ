from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_get_top_movers_success():
    """Test successful retrieval of top NSE movers from endpoint."""
    mock_movers = [
        {"symbol": "APOLLOHOSP", "price": 8876.5, "change": -173.5, "pct_change": -1.92},
        {"symbol": "RELIANCE", "price": 2950.0, "change": 45.0, "pct_change": 1.55},
    ]

    with patch("app.api.v1.routers.market._fetch_top_movers_sync", return_value=mock_movers), \
         patch("app.core.cache.cache.get", return_value=None), \
         patch("app.core.cache.cache.set", return_value=True):

        response = client.get("/api/v1/market/top-movers")
        assert response.status_code == 200
        data = response.json()

        assert "as_of" in data
        assert "market_open" in data
        assert "movers" in data
        assert len(data["movers"]) == 2
        assert data["movers"][0]["symbol"] == "APOLLOHOSP"


def test_get_top_movers_cache_hit():
    """Test serving top movers directly from Redis cache."""
    cached_payload = {
        "as_of": "2026-08-05T10:00:00+05:30",
        "market_open": True,
        "movers": [
            {"symbol": "TCS", "price": 4200.0, "change": 50.0, "pct_change": 1.2}
        ],
    }

    with patch("app.core.cache.cache.get", return_value=cached_payload):
        response = client.get("/api/v1/market/top-movers")
        assert response.status_code == 200
        data = response.json()

        assert data["movers"][0]["symbol"] == "TCS"
