import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import UUID
from loguru import logger

from app.services.financial_intelligence.calculator import MetricCalculator
from app.services.financial_ratios_scraper import normalize_percentage
from app.services.yahoo_finance_summary import _safe_float

def test_metric_calculator_calculate_roe_normal():
    """Verify calculate_roe returns 0-100 percentage scale and correct values."""
    # Net profit 237, Equity 3950 -> 6.0%
    val, prov = MetricCalculator.calculate_roe(237.0, 3950.0)
    assert val == 6.0
    assert prov.metric_name == "roe"

    # Net profit 114.28, Equity 2033.5 -> ~5.62%
    val2, _ = MetricCalculator.calculate_roe(114.28, 2033.5)
    assert round(val2, 2) == 5.62


def test_metric_calculator_calculate_roe_bounds_warning():
    """Verify calculate_roe logs a warning if |ROE| > 200%."""
    messages = []
    sink_id = logger.add(lambda msg: messages.append(msg), level="WARNING")
    try:
        val, _ = MetricCalculator.calculate_roe(500.0, 100.0)  # 500%
        assert val == 500.0
        assert any("exceeds sanity bound" in str(m) for m in messages)
    finally:
        logger.remove(sink_id)


def test_normalize_percentage_fraction_and_percent_scales():
    """Verify normalize_percentage handles both raw decimal fractions and existing percent scale."""
    # Raw decimal fractions (0-1 scale)
    assert normalize_percentage(0.06, input_scale="fraction") == 6.0
    assert normalize_percentage(0.2127, input_scale="fraction") == 21.27
    assert normalize_percentage(-0.15, input_scale="fraction") == -15.0

    # Already on 0-100 percentage scale
    assert normalize_percentage(6.0, input_scale="percent") == 6.0
    assert normalize_percentage(21.27, input_scale="percent") == 21.27
    assert normalize_percentage(5.62, input_scale="percent") == 5.62

    # None and NaN handling
    assert normalize_percentage(None) is None
    assert normalize_percentage(float("nan")) is None


@pytest.mark.asyncio
async def test_financial_summary_endpoint_roe_sane_bound():
    """Integration test asserting GET /api/v1/companies/{id}/financial-summary returns roe < 200."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        # List companies to get a valid fixture company_id
        res = await client.get("/api/v1/companies")
        assert res.status_code == 200
        companies = res.json()
        assert len(companies) > 0, "No companies found in test DB"

        company_id = companies[0]["id"]
        ticker = companies[0]["ticker_symbol"]

        summary_res = await client.get(f"/api/v1/companies/{company_id}/financial-summary")
        assert summary_res.status_code == 200
        data = summary_res.json()

        if data.get("available") and data.get("roe") is not None:
            roe_val = data["roe"]
            assert abs(roe_val) < 200.0, f"ROE value {roe_val}% for company {ticker} exceeds sane bound of 200%"
