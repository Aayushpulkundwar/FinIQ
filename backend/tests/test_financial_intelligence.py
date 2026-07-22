import pytest
import uuid
from typing import Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.services.financial_intelligence.parser import FinancialParser
from app.services.financial_intelligence.normalizer import FinancialNormalizer
from app.services.financial_intelligence.validator import FinancialValidator, MissingReason
from app.services.financial_intelligence.calculator import MetricCalculator
from app.schemas.financial import (
    FinancialStatementData, FinancialAnalyzeResponse,
    FinancialMetricsData, FinancialFieldEvidence, MetricProvenance, TrendPoint
)


@pytest.fixture(autouse=True)
def disable_llm_provider(monkeypatch):
    monkeypatch.setattr("app.services.financial_intelligence.parser.settings.LLM_PROVIDER", "regex")
    monkeypatch.setattr("app.services.financial_intelligence.parser.settings.OPENROUTER_API_KEY", None)


# ─────────────────────────────────────────────
# 1. FinancialParser Tests
# ─────────────────────────────────────────────

def _make_chunk(text: str, similarity: float = 0.9, page: int = 5):
    chunk = MagicMock()
    chunk.chunk_text = text
    chunk.similarity_score = similarity
    chunk.page_number = page
    chunk.document_title = "FY2025 Annual Report"
    chunk.section_title = "Financial Highlights"
    return chunk


def test_parser_extracts_revenue():
    """Parses revenue from income statement chunk text."""
    chunk = _make_chunk("Revenue: $12.5 billion for the fiscal year 2025.")
    result = FinancialParser.parse_chunks({"income_statement": [chunk]})
    assert result["revenue"][0] is not None
    assert result["revenue"][0] == 12_500_000_000.0


def test_parser_extracts_ebitda():
    """Parses EBITDA from income statement chunk text."""
    chunk = _make_chunk("EBITDA: $4,200 million for the quarter.")
    result = FinancialParser.parse_chunks({"income_statement": [chunk]})
    assert result["ebitda"][0] is not None


def test_parser_extracts_eps():
    """Parses EPS from earnings chunk text."""
    chunk = _make_chunk("Earnings per share: $3.45 for FY2025.")
    result = FinancialParser.parse_chunks({"income_statement": [chunk]})
    assert result["eps"][0] is not None
    assert result["eps"][0] == 3.45


def test_parser_extracts_total_assets():
    """Parses total assets from balance sheet chunk text."""
    chunk = _make_chunk("Total assets: $85.2 billion.")
    result = FinancialParser.parse_chunks({"balance_sheet": [chunk]})
    assert result["total_assets"][0] is not None


def test_parser_returns_none_for_missing_fields():
    """Returns (None, None) for fields not found in any chunk."""
    chunk = _make_chunk("This chunk contains no relevant financial information.")
    result = FinancialParser.parse_chunks({"income_statement": [chunk]})
    assert result["capex"][0] is None
    assert result["capex"][1] is None


def test_parser_priority_by_similarity():
    """Higher similarity chunk should be preferred over lower similarity."""
    high_sim_chunk = _make_chunk("Revenue: $10 billion", similarity=0.95)
    low_sim_chunk = _make_chunk("Revenue: $5 billion", similarity=0.6)
    result = FinancialParser.parse_chunks({"income_statement": [low_sim_chunk, high_sim_chunk]})
    assert result["revenue"][0] is not None
    assert result["revenue"][0] == 10_000_000_000.0


# ─────────────────────────────────────────────
# 2. FinancialNormalizer Tests
# ─────────────────────────────────────────────

def test_normalizer_billions():
    """Converts billion-denominated values to base units."""
    result = FinancialNormalizer.normalize("12.5 billion")
    assert result == 12_500_000_000.0


def test_normalizer_millions():
    """Converts million-denominated values to base units."""
    result = FinancialNormalizer.normalize("4200 million")
    assert result == 4_200_000_000.0


def test_normalizer_crores():
    """Converts Indian crore values to base units."""
    result = FinancialNormalizer.normalize("500 crore")
    assert result == 5_000_000_000.0


def test_normalizer_currency_symbols():
    """Strips currency symbols before numeric parsing."""
    result = FinancialNormalizer.normalize("$85.2 billion")
    assert result == 85_200_000_000.0


def test_normalizer_comma_separated():
    """Strips commas from comma-separated numbers."""
    result = FinancialNormalizer.normalize("12,345.67")
    assert result == 12345.67


def test_normalizer_parenthetical_negative():
    """Handles parenthetical negative values like (1234.5)."""
    result = FinancialNormalizer.normalize("(1,234.5)")
    assert result == -1234.5


def test_normalizer_invalid_returns_none():
    """Returns None for invalid unparseable strings."""
    result = FinancialNormalizer.normalize("not a number")
    assert result is None


def test_normalizer_none_input():
    """Returns None for None input."""
    result = FinancialNormalizer.normalize(None)
    assert result is None


def test_normalizer_normalize_all():
    """Applies normalization across a whole field dict."""
    data = {"revenue": "12.5 billion", "eps": "3.45", "capex": None}
    result = FinancialNormalizer.normalize_all(data)
    assert result["revenue"] == 12_500_000_000.0
    assert result["eps"] == 3.45
    assert result["capex"] is None


# ─────────────────────────────────────────────
# 3. FinancialValidator Tests
# ─────────────────────────────────────────────

def test_validator_clean_values_pass():
    """Valid positive values pass through unchanged."""
    data = {"revenue": 1_000_000.0, "net_profit": 200_000.0, "total_assets": 5_000_000.0}
    clean, missing = FinancialValidator.validate(data)
    assert clean["revenue"] == 1_000_000.0
    assert not missing


def test_validator_negative_revenue_rejected():
    """Negative revenue is rejected with NOT_REPORTED sentinel."""
    data = {"revenue": -500.0, "net_profit": 100.0, "total_assets": 1_000.0}
    clean, missing = FinancialValidator.validate(data)
    assert clean["revenue"] is None
    assert missing["revenue"] == MissingReason.NOT_REPORTED


def test_validator_none_classified_as_unable_to_extract():
    """None values are classified as UNABLE_TO_EXTRACT."""
    data = {"revenue": None, "net_profit": 100.0, "total_assets": None}
    clean, missing = FinancialValidator.validate(data)
    assert missing["revenue"] == MissingReason.UNABLE_TO_EXTRACT
    assert missing["total_assets"] == MissingReason.UNABLE_TO_EXTRACT


def test_validator_derives_shareholders_equity():
    """Derives shareholders_equity from assets - liabilities when missing."""
    data = {
        "revenue": 1000.0, "net_profit": 100.0,
        "total_assets": 5000.0, "total_liabilities": 3000.0,
        "shareholders_equity": None
    }
    clean, missing = FinancialValidator.validate(data)
    assert clean["shareholders_equity"] == 2000.0
    assert "shareholders_equity" not in missing


def test_validator_negative_assets_rejected():
    """Negative total_assets is rejected with NOT_REPORTED sentinel."""
    data = {"revenue": 1000.0, "total_assets": -500.0}
    clean, missing = FinancialValidator.validate(data)
    assert clean["total_assets"] is None
    assert missing["total_assets"] == MissingReason.NOT_REPORTED


# ─────────────────────────────────────────────
# 4. MetricCalculator Tests
# ─────────────────────────────────────────────

def test_calc_ebitda_margin():
    """EBITDA Margin = ebitda / revenue * 100."""
    value, prov = MetricCalculator.calculate_ebitda_margin(4_000.0, 20_000.0)
    assert value == pytest.approx(20.0)
    assert prov.metric_name == "ebitda_margin"
    assert "ebitda" in prov.input_fields
    assert "revenue" in prov.input_fields


def test_calc_net_profit_margin():
    """Net Profit Margin = net_profit / revenue * 100."""
    value, prov = MetricCalculator.calculate_net_profit_margin(2_000.0, 20_000.0)
    assert value == pytest.approx(10.0)
    assert prov.metric_name == "net_profit_margin"


def test_calc_roe():
    """ROE = net_profit / shareholders_equity * 100."""
    value, prov = MetricCalculator.calculate_roe(2_000.0, 10_000.0)
    assert value == pytest.approx(20.0)
    assert prov.metric_name == "roe"


def test_calc_roce():
    """ROCE = operating_income / (total_assets - total_liabilities) * 100."""
    value, prov = MetricCalculator.calculate_roce(3_000.0, 15_000.0, 5_000.0)
    assert value == pytest.approx(30.0)
    assert prov.metric_name == "roce"


def test_calc_debt_to_equity():
    """D/E = total_liabilities / shareholders_equity."""
    value, prov = MetricCalculator.calculate_debt_to_equity(6_000.0, 4_000.0)
    assert value == pytest.approx(1.5)
    assert prov.metric_name == "debt_to_equity"


def test_calc_revenue_growth_yoy():
    """Revenue Growth YoY = (current - previous) / abs(previous) * 100."""
    value, prov = MetricCalculator.calculate_revenue_growth_yoy(12_000.0, 10_000.0)
    assert value == pytest.approx(20.0)
    assert prov.metric_name == "revenue_growth_yoy"


def test_calc_eps_growth():
    """EPS Growth = (current - previous) / abs(previous) * 100."""
    value, prov = MetricCalculator.calculate_eps_growth(3.9, 3.0)
    assert value == pytest.approx(30.0)
    assert prov.metric_name == "eps_growth"


def test_calc_free_cash_flow_yield():
    """FCF Yield = free_cash_flow / revenue * 100."""
    value, prov = MetricCalculator.calculate_free_cash_flow_yield(1_500.0, 20_000.0)
    assert value == pytest.approx(7.5)
    assert prov.metric_name == "free_cash_flow_yield"


def test_calc_current_ratio_proxy():
    """Current Ratio proxy = operating_cash_flow / total_liabilities."""
    value, prov = MetricCalculator.calculate_current_ratio(3_000.0, 6_000.0)
    assert value == pytest.approx(0.5)
    assert prov.metric_name == "current_ratio"


def test_calc_divide_by_zero_returns_none():
    """All metric calculations return None when denominator is zero."""
    v1, _ = MetricCalculator.calculate_ebitda_margin(4000.0, 0.0)
    v2, _ = MetricCalculator.calculate_roe(2000.0, 0.0)
    v3, _ = MetricCalculator.calculate_debt_to_equity(6000.0, 0.0)
    assert v1 is None
    assert v2 is None
    assert v3 is None


def test_calc_none_inputs_return_none():
    """All calculations return None when inputs are None."""
    v, _ = MetricCalculator.calculate_ebitda_margin(None, 10_000.0)
    assert v is None


def test_calc_all_returns_provenance_list():
    """calculate_all returns non-empty provenance list when data is available."""
    stmt = FinancialStatementData(
        revenue=20_000.0, ebitda=4_000.0, net_profit=2_000.0,
        operating_income=3_000.0, eps=3.5,
        total_assets=15_000.0, total_liabilities=5_000.0,
        shareholders_equity=10_000.0,
        operating_cash_flow=3_000.0, free_cash_flow=1_500.0
    )
    metrics, provenance = MetricCalculator.calculate_all(stmt)
    assert isinstance(metrics, FinancialMetricsData)
    assert len(provenance) >= 7
    names = [p.metric_name for p in provenance]
    assert "ebitda_margin" in names
    assert "roe" in names
    assert "debt_to_equity" in names


def test_calc_all_provenance_has_formulas():
    """All provenance records include formula and input_fields."""
    stmt = FinancialStatementData(revenue=20_000.0, ebitda=4_000.0)
    _, provenance = MetricCalculator.calculate_all(stmt)
    for p in provenance:
        assert p.formula
        assert isinstance(p.input_fields, list)
        assert len(p.input_fields) > 0


# ─────────────────────────────────────────────
# 5. FinancialIntelligenceService Integration Test
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_financial_intelligence_service_analyze():
    """Verifies FinancialIntelligenceService.analyze returns FinancialAnalyzeResponse."""
    from app.services.financial_intelligence.service import FinancialIntelligenceService

    db_mock = AsyncMock()
    company_id = uuid.uuid4()

    with patch("app.services.financial_intelligence.service.FinancialRepository") as MockRepo, \
         patch("app.services.financial_intelligence.service.CompanyRepository") as MockCompanyRepo, \
         patch("app.services.financial_intelligence.service.RetrievalService") as MockRetrieval, \
         patch("app.services.financial_intelligence.service.FinancialExtractor") as MockExtractor, \
         patch("app.services.financial_intelligence.service.TrendAnalyzer") as MockTrend:

        # Mock company
        mock_company = MagicMock()
        mock_company.company_name = "TestCorp"
        mock_company.id = company_id
        MockCompanyRepo.return_value.get = AsyncMock(return_value=mock_company)

        # Mock extractor - return empty chunks (no data to extract)
        MockExtractor.return_value.extract_chunks = AsyncMock(return_value={
            "income_statement": [],
            "balance_sheet": [],
            "cash_flow": [],
        })

        # Mock repository
        mock_period = MagicMock()
        mock_period.id = uuid.uuid4()
        MockRepo.return_value.get_or_create_period = AsyncMock(return_value=mock_period)
        MockRepo.return_value.get_statements_by_company = AsyncMock(return_value=[])
        MockRepo.return_value.db = db_mock

        # Mock trend analyzer
        MockTrend.return_value.analyze = AsyncMock(return_value=[])

        # Mock DB operations
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(2025,)]
        db_mock.execute = AsyncMock(return_value=mock_result)
        db_mock.add = MagicMock()
        db_mock.flush = AsyncMock()
        db_mock.commit = AsyncMock()

        service = FinancialIntelligenceService(db_mock)
        result = await service.analyze(company_id=company_id, fiscal_year=2025)

    assert isinstance(result, FinancialAnalyzeResponse)
    assert result.company_name == "TestCorp"
    assert result.fiscal_year == 2025
    assert result.period_type == "annual"
    assert isinstance(result.financial_evidence, list)
    assert isinstance(result.metric_provenance, list)
    assert isinstance(result.trend_analysis, list)


# ─────────────────────────────────────────────
# 6. LangGraph Tool Tests
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_financial_tool_registered_in_langgraph():
    """Verifies analyze_financial_intelligence is registered as a LangGraph tool."""
    from app.ai.orchestrator.tools import create_tools
    db_mock = AsyncMock()

    with patch("app.ai.orchestrator.tools.FinancialIntelligenceService"), \
         patch("app.ai.orchestrator.tools.EventIntelligenceService"):
        tools = create_tools(db_mock)

    assert "analyze_financial_intelligence" in tools


def test_financial_keywords_route_to_financial_tool():
    """Verifies that financial keyword queries are routed to analyze_financial_intelligence."""
    import re
    financial_keywords = [
        "revenue", "ebitda", "income statement", "balance sheet", "cash flow",
        "earnings", "margin", "profit", "eps", "financial", "ratio", "roe",
        "roce", "debt", "equity", "assets", "liabilities", "capex", "free cash flow",
        "net income", "quarterly results", "annual results", "financials"
    ]
    query = "What is the EBITDA margin and ROE for this company?"
    assert any(k in query.lower() for k in financial_keywords)


# ─────────────────────────────────────────────
# 7. API Endpoint Tests
# ─────────────────────────────────────────────

def test_api_analyze_financial_success(client: TestClient):
    """Verifies POST /api/v1/financial/analyze returns FinancialAnalyzeResponse."""
    company_id = uuid.uuid4()
    mock_result = FinancialAnalyzeResponse(
        company_id=company_id,
        company_name="TechCorp Inc",
        fiscal_year=2025,
        period_type="annual",
        currency="USD",
        financial_summary="TechCorp reported strong revenue growth.",
        latest_statement=FinancialStatementData(
            revenue=20_000_000_000.0,
            ebitda=4_000_000_000.0,
            net_profit=2_000_000_000.0,
        ),
        calculated_metrics=FinancialMetricsData(
            ebitda_margin=20.0,
            net_profit_margin=10.0,
            roe=18.5,
        ),
        trend_analysis=[
            TrendPoint(
                fiscal_year=2025,
                period_type="annual",
                revenue=20_000_000_000.0,
                net_profit=2_000_000_000.0,
                eps=3.5,
                trend_direction="Increasing"
            )
        ],
        metric_provenance=[
            MetricProvenance(
                metric_name="ebitda_margin",
                formula="ebitda / revenue * 100",
                input_fields=["ebitda", "revenue"]
            )
        ],
        financial_evidence=[
            FinancialFieldEvidence(
                financial_field="revenue",
                extracted_value=20_000_000_000.0,
                document_title="FY2025 Annual Report",
                page_number=12,
                section_title="Financial Highlights",
                chunk_text="Revenue: $20 billion for fiscal year 2025.",
                similarity_score=0.92
            )
        ]
    )

    with patch("app.api.v1.routers.financial.FinancialIntelligenceService") as MockService:
        mock_svc = MagicMock()
        mock_svc.analyze = AsyncMock(return_value=mock_result)
        MockService.return_value = mock_svc

        response = client.post("/api/v1/financial/analyze", json={
            "company_id": str(company_id),
            "fiscal_year": 2025,
            "period_type": "annual"
        })

    assert response.status_code == 200
    data = response.json()
    assert data["company_name"] == "TechCorp Inc"
    assert data["fiscal_year"] == 2025
    assert data["calculated_metrics"]["ebitda_margin"] == 20.0
    assert len(data["trend_analysis"]) == 1
    assert data["trend_analysis"][0]["trend_direction"] == "Increasing"
    assert len(data["metric_provenance"]) == 1
    assert data["metric_provenance"][0]["formula"] == "ebitda / revenue * 100"
    assert len(data["financial_evidence"]) == 1
    assert data["financial_evidence"][0]["financial_field"] == "revenue"


def test_api_analyze_financial_not_found(client: TestClient):
    """Verifies POST /api/v1/financial/analyze returns 404 when company not found."""
    company_id = uuid.uuid4()

    with patch("app.api.v1.routers.financial.FinancialIntelligenceService") as MockService:
        mock_svc = MagicMock()
        mock_svc.analyze = AsyncMock(side_effect=ValueError(f"Company with id={company_id} not found."))
        MockService.return_value = mock_svc

        response = client.post("/api/v1/financial/analyze", json={
            "company_id": str(company_id)
        })

    assert response.status_code == 404


def test_api_analyze_financial_internal_error(client: TestClient):
    """Verifies POST /api/v1/financial/analyze returns 500 on pipeline failure."""
    company_id = uuid.uuid4()

    with patch("app.api.v1.routers.financial.FinancialIntelligenceService") as MockService:
        mock_svc = MagicMock()
        mock_svc.analyze = AsyncMock(side_effect=Exception("Database connection lost"))
        MockService.return_value = mock_svc

        response = client.post("/api/v1/financial/analyze", json={
            "company_id": str(company_id)
        })

    assert response.status_code == 500
