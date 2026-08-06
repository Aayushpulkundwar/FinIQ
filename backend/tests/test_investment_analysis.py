import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.services.valuation import ValuationService
from app.services.research_report import ResearchReportService
from app.schemas.investment import (
    InvestmentAnalyzeResponse, ValuationSummary, WaccDetails, DcfDetails, SensitivityPoint
)
from app.schemas.financial import FinancialAnalyzeResponse, FinancialStatementData, FinancialMetricsData
from app.schemas.response_generation import AIResponse


# ─────────────────────────────────────────────
# 1. ValuationService Unit Tests
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_valuation_service_calculation():
    """Verifies WACC, DCF, and Sensitivity analysis math models compute correctly."""
    db_mock = AsyncMock()
    company_id = uuid.uuid4()

    # Mock Financial Statement and Ratios from FinancialIntelligenceService
    mock_statement = FinancialStatementData(
        revenue=10_000_000_000.0,
        ebitda=3_000_000_000.0,
        operating_income=2_500_000_000.0,
        net_profit=1_500_000_000.0,
        eps=1.5,
        total_assets=30_000_000_000.0,
        total_liabilities=10_000_000_000.0,
        shareholders_equity=20_000_000_000.0,
        operating_cash_flow=2_000_000_000.0,
        free_cash_flow=1_200_000_000.0,
        capex=800_000_000.0,
    )
    mock_metrics = FinancialMetricsData(
        revenue_growth_yoy=10.0,
        ebitda_margin=30.0,
        net_profit_margin=15.0,
    )
    mock_fin_report = FinancialAnalyzeResponse(
        company_id=company_id,
        company_name="TechCorp Inc",
        fiscal_year=2025,
        period_type="annual",
        currency="USD",
        financial_summary="Test financial summary",
        latest_statement=mock_statement,
        calculated_metrics=mock_metrics,
        trend_analysis=[],
        metric_provenance=[],
        financial_evidence=[]
    )

    with patch("app.services.valuation.FinancialIntelligenceService") as MockFinSvc, \
         patch("app.services.valuation.CompanyService") as MockCompSvc:
        
        # Mock financial service analyze call
        MockFinSvc.return_value.analyze = AsyncMock(return_value=mock_fin_report)
        
        # Mock company metadata
        mock_company = MagicMock()
        mock_company.company_name = "TechCorp Inc"
        mock_company.sector = "Technology"
        MockCompSvc.return_value.repository.get = AsyncMock(return_value=mock_company)

        valuation_svc = ValuationService(db_mock)
        summary = await valuation_svc.calculate_valuation(company_id=company_id, fiscal_year=2025)

    assert isinstance(summary, ValuationSummary)
    assert summary.wacc_details.wacc > 0
    assert summary.dcf_details.intrinsic_share_price > 0
    assert len(summary.sensitivity_grid) == 25  # 5x5 variations
    assert summary.confidence_score == 1.0     # all fields present


@pytest.mark.asyncio
async def test_valuation_service_capital_weight_fallbacks():
    """Verifies that WACC calculations fall back gracefully to 80/20 weights when values are missing."""
    db_mock = AsyncMock()
    company_id = uuid.uuid4()

    mock_statement = FinancialStatementData(
        revenue=None,
        total_liabilities=None,
        shareholders_equity=None,
        operating_income=100.0,
        ebitda=None,
        capex=10.0,
        net_profit=50.0,
        operating_cash_flow=80.0,
    )
    mock_metrics = FinancialMetricsData()
    mock_fin_report = FinancialAnalyzeResponse(
        company_id=company_id, company_name="MockCorp", fiscal_year=2025, period_type="annual", currency="USD",
        financial_summary="Test", latest_statement=mock_statement, calculated_metrics=mock_metrics,
        trend_analysis=[], metric_provenance=[], financial_evidence=[]
    )

    with patch("app.services.valuation.FinancialIntelligenceService") as MockFinSvc, \
         patch("app.services.valuation.CompanyService") as MockCompSvc:
        MockFinSvc.return_value.analyze = AsyncMock(return_value=mock_fin_report)
        MockCompSvc.return_value.repository.get = AsyncMock(return_value=None)

        valuation_svc = ValuationService(db_mock)
        summary = await valuation_svc.calculate_valuation(company_id=company_id, fiscal_year=2025)

    assert summary.wacc_details.equity_weight == 0.80
    assert summary.wacc_details.debt_weight == 0.20
    assert summary.confidence_score == 0.0  # missing all fields



@pytest.mark.asyncio
async def test_valuation_service_capex_and_fcf_fallbacks():
    """Verifies that ValuationService successfully calculates valuation with fallback UFCF when FCF and CapEx are missing."""
    db_mock = AsyncMock()
    company_id = uuid.uuid4()

    mock_statement = FinancialStatementData(
        revenue=1_000_000_000.0,
        total_liabilities=200_000_000.0,
        shareholders_equity=800_000_000.0,
        operating_income=100_000_000.0,
        ebitda=120_000_000.0,
        capex=None,                # Missing CapEx -> should fallback to 0.0
        free_cash_flow=None,       # Missing FCF -> should calculate UFCF
        net_profit=50_000_000.0,
        operating_cash_flow=80_000_000.0,
    )
    mock_metrics = FinancialMetricsData(
        revenue_growth_yoy=5.0
    )
    mock_fin_report = FinancialAnalyzeResponse(
        company_id=company_id, company_name="MockCorp", fiscal_year=2025, period_type="annual", currency="USD",
        financial_summary="Test", latest_statement=mock_statement, calculated_metrics=mock_metrics,
        trend_analysis=[], metric_provenance=[], financial_evidence=[]
    )

    with patch("app.services.valuation.FinancialIntelligenceService") as MockFinSvc, \
         patch("app.services.valuation.CompanyService") as MockCompSvc:
        MockFinSvc.return_value.analyze = AsyncMock(return_value=mock_fin_report)
        MockCompSvc.return_value.repository.get = AsyncMock(return_value=None)

        valuation_svc = ValuationService(db_mock)
        summary = await valuation_svc.calculate_valuation(company_id=company_id, fiscal_year=2025)

    assert summary.dcf_details.baseline_fcf > 0
    # UFCF = EBIT*(1-0.21) + Dep - CapEx - WCap
    # Dep = 120M - 100M = 20M
    # CapEx = 0.0
    # WCap = 50M + 20M - 80M = -10M
    # UFCF = 100M * 0.79 + 20M - 0.0 - (-10M) = 79M + 20M + 10M = 109.0M
    assert summary.dcf_details.baseline_fcf == 109_000_000.0
    assert summary.dcf_details.intrinsic_share_price > 0


# ─────────────────────────────────────────────
# 2. ResearchReportService Unit Tests
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_research_report_generation():
    """Verifies that ResearchReportService aggregates reports and invokes response generation."""
    db_mock = AsyncMock()
    company_id = uuid.uuid4()

    mock_statement = FinancialStatementData(revenue=1000.0, net_profit=100.0)
    mock_metrics = FinancialMetricsData(revenue_growth_yoy=5.0, ebitda_margin=10.0, debt_to_equity=0.5)
    mock_fin_report = FinancialAnalyzeResponse(
        company_id=company_id, company_name="MockCorp", fiscal_year=2025, period_type="annual", currency="USD",
        financial_summary="Test Summary", latest_statement=mock_statement, calculated_metrics=mock_metrics,
        trend_analysis=[], metric_provenance=[], financial_evidence=[]
    )

    mock_wacc = WaccDetails(cost_of_equity=0.1, cost_of_debt=0.05, equity_weight=0.8, debt_weight=0.2, wacc=0.09)
    mock_dcf = DcfDetails(
        baseline_fcf=100.0, fcf_growth_rate=0.05, projected_fcfs=[105, 110, 115, 120, 126],
        terminal_growth_rate=0.02, terminal_value=1800, enterprise_value=1500, equity_value=1400,
        shares_outstanding=100, intrinsic_share_price=14.0
    )
    mock_val_summary = ValuationSummary(
        wacc_details=mock_wacc, dcf_details=mock_dcf, sensitivity_grid=[], confidence_score=0.8
    )

    with patch("app.services.research_report.CompanyService") as MockCompSvc, \
         patch("app.services.research_report.FinancialIntelligenceService") as MockFinSvc, \
         patch("app.services.research_report.ValuationService") as MockValSvc, \
         patch("app.services.research_report.RetrievalService") as MockRetrieval, \
         patch("app.services.research_report.ResponseGenerationService") as MockGenSvc:

        mock_company = MagicMock()
        mock_company.company_name = "MockCorp"
        mock_company.ticker_symbol = "MCKP"
        MockCompSvc.return_value.repository.get = AsyncMock(return_value=mock_company)

        MockFinSvc.return_value.analyze = AsyncMock(return_value=mock_fin_report)
        MockValSvc.return_value.calculate_valuation = AsyncMock(return_value=mock_val_summary)
        MockRetrieval.return_value.search = AsyncMock(return_value=[])

        # Mock ResponseGenerationService response
        mock_ai_resp = AIResponse(
            executive_summary="Institutional summary.",
            key_insights=["Insight A", "Insight B"],
            supporting_evidence=["Evidence 1"],
            risks_limitations=["Risk X"],
            sources=["Document Y"],
            error_message=None
        )
        MockGenSvc.return_value.generate_response = AsyncMock(return_value=mock_ai_resp)

        report_svc = ResearchReportService(db_mock)
        report_md = await report_svc.generate_report(company_id=company_id, fiscal_year=2025)

    assert "INVESTMENT RESEARCH REPORT: MockCorp (MCKP)" in report_md
    assert "Executive Summary" in report_md
    assert "Est. Intrinsic share price: $14.0" or "Estimated Intrinsic share price: $14.0" in report_md


# ─────────────────────────────────────────────
# 3. LangGraph Routing Tests
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_langgraph_investment_tools_registered():
    """Verifies valuation and research report tools register with LangGraph."""
    from app.ai.orchestrator.tools import create_tools
    db_mock = AsyncMock()

    with patch("app.ai.orchestrator.tools.FinancialIntelligenceService"), \
         patch("app.ai.orchestrator.tools.EventIntelligenceService"), \
         patch("app.ai.orchestrator.tools.ValuationService"), \
         patch("app.ai.orchestrator.tools.ResearchReportService"):
        tools = create_tools(db_mock)

    assert "calculate_company_valuation" in tools
    assert "generate_research_report" in tools


def test_fallback_router_valuation_routing():
    """Verifies that fallback routing rules correctly match investment keywords."""
    valuation_keywords = ["valuation", "dcf", "wacc", "intrinsic", "discounted cash", "sensitivity"]
    report_keywords = ["research report", "investment report", "report generator", "analyst report"]

    q1 = "Estimate the DCF valuation and WACC of TSLA."
    q2 = "Build a research report for AAPL."

    assert any(k in q1.lower() for k in valuation_keywords)
    assert any(k in q2.lower() for k in report_keywords)


# ─────────────────────────────────────────────
# 4. API Router Tests
# ─────────────────────────────────────────────

def test_api_investment_analyze_success(client: TestClient):
    """Verifies POST /api/v1/investment/analyze enqueues task and returns 202 response."""
    company_id = uuid.uuid4()

    with patch("app.api.v1.routers.investment.run_investment_analysis_task") as mock_task:
        mock_task.delay.return_value.id = "test-task-id-123"
        mock_task.delay.return_value.status = "PENDING"

        response = client.post("/api/v1/investment/analyze", json={
            "company_id": str(company_id),
            "fiscal_year": 2025
        })

    assert response.status_code == 202
    data = response.json()
    assert data["task_id"] == "test-task-id-123"
    assert data["status"] == "PENDING"


def test_api_investment_analyze_not_found(client: TestClient):
    """Verifies POST /api/v1/investment/analyze returns 500 when task enqueue fails."""
    company_id = uuid.uuid4()

    with patch("app.api.v1.routers.investment.run_investment_analysis_task") as mock_task:
        mock_task.delay.side_effect = Exception("Celery task queue connection error")

        response = client.post("/api/v1/investment/analyze", json={
            "company_id": str(company_id)
        })

    assert response.status_code == 500


def test_api_company_recommendation_success(client: TestClient):
    """Verifies GET /api/v1/companies/{id}/recommendation computes signal successfully."""
    company_id = uuid.uuid4()
    
    mock_company = MagicMock()
    mock_company.ticker_symbol = "AAPL"
    mock_company.exchange = "NASDAQ"

    mock_dcf_inputs = {
        "available": True,
        "current_price": 150.0,
        "free_cash_flow": 80_000_000_000.0,
        "shares_outstanding": 15_000_000_000.0,
        "fcf_growth_rate": 0.05,
        "currency": "USD",
        "cash": 50_000_000_000.0,
        "debt": 100_000_000_000.0,
        "ebit": 100_000_000_000.0,
        "depreciation": 10_000_000_000.0,
        "capex": 5_000_000_000.0,
        "change_in_working_capital": 2_000_000_000.0,
        "tax_rate": 0.21,
        "net_profit": 80_000_000_000.0,
        "ebitda": 110_000_000_000.0,
    }

    # Under 10% WACC, FCF of 80B on 15B shares produces:
    # intrinsic share price > 150 (Buy)
    with patch("app.api.v1.routers.company.CompanyService") as MockCompSvc, \
         patch("app.api.v1.routers.company.get_yfinance_dcf_inputs") as MockInputs:
        
        MockCompSvc.return_value.get_company = AsyncMock(return_value=mock_company)
        MockInputs.return_value = mock_dcf_inputs

        response = client.get(f"/api/v1/companies/{company_id}/recommendation")

    assert response.status_code == 200
    data = response.json()
    assert data["signal"] in ["Buy", "Hold", "Sell"]
    assert data["current_price"] == 150.0
    assert data["intrinsic_value"] > 0


def test_api_company_recommendation_sanity_failure(client: TestClient):
    """Verifies GET /api/v1/companies/{id}/recommendation fails sanity checks on extreme valuation."""
    company_id = uuid.uuid4()
    
    mock_company = MagicMock()
    mock_company.ticker_symbol = "AAPL"
    mock_company.exchange = "NASDAQ"

    # Extreme cash flow / very low shares outstanding resulting in a massive valuation
    mock_dcf_inputs = {
        "available": True,
        "current_price": 10.0,
        "free_cash_flow": 10_000_000_000.0,
        "shares_outstanding": 100.0,       # Insanely small shares -> price will be in the millions
        "fcf_growth_rate": 0.05,
        "currency": "USD",
        "cash": 100.0,
        "debt": 100.0,
        "ebit": 100.0,
        "depreciation": 10.0,
        "capex": 5.0,
        "change_in_working_capital": 2.0,
        "tax_rate": 0.21,
        "net_profit": 50.0,
        "ebitda": 110.0,
    }

    with patch("app.api.v1.routers.company.CompanyService") as MockCompSvc, \
         patch("app.api.v1.routers.company.get_yfinance_dcf_inputs") as MockInputs:
        
        MockCompSvc.return_value.get_company = AsyncMock(return_value=mock_company)
        MockInputs.return_value = mock_dcf_inputs

        response = client.get(f"/api/v1/companies/{company_id}/recommendation")

    assert response.status_code == 200
    data = response.json()
    assert data["signal"] == "Unavailable"
    assert data["reason"] == "failed_sanity_checks"

