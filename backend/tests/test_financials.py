import pytest
import pandas as pd
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
from app.models.company import Company


@pytest.fixture
def mock_yf_data():
    years = [pd.Timestamp("2026-12-31"), pd.Timestamp("2025-12-31")]
    df_inc = pd.DataFrame(
        {
            years[0]: [1000.0, 500.0, 200.0, 300.0, 150.0, 1.5, 1.4],
            years[1]: [800.0, 400.0, 160.0, 240.0, 120.0, 1.2, 1.1],
        },
        index=[
            "Total Revenue",
            "Gross Profit",
            "Operating Income",
            "EBITDA",
            "Net Income",
            "Basic EPS",
            "Diluted EPS",
        ],
    )
    
    df_q_inc = pd.DataFrame(
        {
            pd.Timestamp("2026-09-30"): [250.0, 120.0, 50.0, 75.0, 35.0, 0.35, 0.33],
        },
        index=[
            "Total Revenue",
            "Gross Profit",
            "Operating Income",
            "EBITDA",
            "Net Income",
            "Basic EPS",
            "Diluted EPS",
        ],
    )

    df_bal = pd.DataFrame(
        {
            years[0]: [300.0, 500.0, 1000.0],
            years[1]: [250.0, 400.0, 800.0],
        },
        index=[
            "Total Debt",
            "Stockholders Equity",
            "Total Assets",
        ]
    )

    info = {
        "currency": "USD",
        "returnOnEquity": 0.30,
        "returnOnAssets": 0.15,
        "grossMargins": 0.50,
        "operatingMargins": 0.20,
        "profitMargins": 0.15,
        "debtToEquity": 60.0,
        "nextFiscalYearEnd": 1798761600,
    }

    return df_inc, df_q_inc, df_bal, info


@patch("yfinance.Ticker")
def test_get_company_detailed_financials_success(mock_ticker_class, mock_yf_data, client, mock_db):
    df_inc, df_q_inc, df_bal, info = mock_yf_data
    
    mock_ticker = MagicMock()
    mock_ticker.income_stmt = df_inc
    mock_ticker.quarterly_income_stmt = df_q_inc
    mock_ticker.balance_sheet = df_bal
    mock_ticker.info = info
    mock_ticker_class.return_value = mock_ticker

    # Mock DB company lookup
    mock_db.execute = AsyncMock()
    mock_company = Company(
        id="c5b2a3d0-eb9a-4c28-9411-cf0b5a1fe188",
        ticker_symbol="NVDA",
        company_name="NVIDIA Corporation",
        exchange="NASDAQ",
        sector="Technology",
        industry="Semiconductors",
        isin="US67066G1040"
    )

    with patch("app.repositories.company.CompanyRepository.get_by_ticker", return_value=mock_company):
        response = client.get("/api/company/NVDA/financials")
        
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["ticker"] == "NVDA"
    assert res_data["currency"] == "USD"
    assert len(res_data["annual"]) == 2
    assert res_data["annual"][0]["period"] == "FY2026"
    assert res_data["annual"][0]["revenue"] == 1000.0
    assert res_data["annual"][0]["revenue_yoy_pct"] == pytest.approx(25.0)
    assert res_data["annual"][0]["ebitda_yoy_pct"] == pytest.approx(25.0)
    assert res_data["annual"][0]["net_income_yoy_pct"] == pytest.approx(25.0)
    assert res_data["ratios"]["roe_pct"] == 30.0
    assert res_data["ratios"]["debt_to_equity"] == 60.0
