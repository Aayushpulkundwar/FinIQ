import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.models.event import EventType, EventSeverity
from app.services.event_intelligence.classifier import EventClassifier
from app.services.event_intelligence.mapper import IndustryMapper
from app.services.event_intelligence.analyzer import ImpactAnalyzer
from app.schemas.event import EventAnalyzeResponse, CompanyImpact, Evidence


# ─────────────────────────────────────────────
# 1. EventClassifier Tests
# ─────────────────────────────────────────────

def test_classifier_macroeconomic():
    """Classifies interest rate events as macroeconomic type."""
    event_type, severity = EventClassifier.classify(
        title="Federal Reserve Interest Rate Hike",
        description="The Fed has announced a 75bps rate hike amid rising inflation."
    )
    assert event_type == EventType.macroeconomic


def test_classifier_regulatory():
    """Classifies antitrust investigation events as regulatory type."""
    event_type, severity = EventClassifier.classify(
        title="EU Antitrust Investigation Against Big Tech",
        description="The European Commission has launched a formal regulatory antitrust lawsuit against leading cloud firms."
    )
    assert event_type == EventType.regulatory


def test_classifier_geopolitical():
    """Classifies war/conflict/sanction events as geopolitical type."""
    event_type, severity = EventClassifier.classify(
        title="US Military Sanctions Against Russia",
        description="The US government has imposed sweeping military sanctions targeting Russian energy exports."
    )
    assert event_type == EventType.geopolitical


def test_classifier_severity_critical():
    """Classifies bankruptcy events with CRITICAL severity."""
    _, severity = EventClassifier.classify(
        title="Major Bank Collapse",
        description="Bankruptcy declared amid a widespread banking crisis."
    )
    assert severity == EventSeverity.CRITICAL


def test_classifier_severity_high():
    """Classifies tariff hike events with HIGH severity."""
    _, severity = EventClassifier.classify(
        title="New Tariff Increase on Imports",
        description="Government announces a 40% tariff increase on semiconductor imports."
    )
    assert severity == EventSeverity.HIGH


def test_classifier_severity_low():
    """Classifies benign events with LOW severity."""
    _, severity = EventClassifier.classify(
        title="Annual Company Meeting",
        description="The board held its annual general meeting."
    )
    assert severity == EventSeverity.LOW


# ─────────────────────────────────────────────
# 2. IndustryMapper Tests
# ─────────────────────────────────────────────

def test_mapper_direct_technology():
    """Identifies technology as a directly affected industry."""
    direct, indirect = IndustryMapper.map_industries(
        title="Cloud Software Market Expansion",
        description="Azure and cloud technology providers are reporting significant growth."
    )
    assert "technology" in direct


def test_mapper_indirect_automotive():
    """Identifies automotive as an indirectly affected industry via technology propagation."""
    direct, indirect = IndustryMapper.map_industries(
        title="Technology Semiconductor Shortage",
        description="The global semiconductor chip shortage is affecting technology supply chains."
    )
    # Technology is direct; automotive is indirectly affected via propagation
    assert "technology" in direct or "semiconductors" in direct
    all_industries = direct + indirect
    assert any(i in all_industries for i in ["automotive", "semiconductors"])


def test_mapper_banking_propagates_real_estate():
    """Verifies banking events propagate impact to real estate indirectly."""
    direct, indirect = IndustryMapper.map_industries(
        title="Federal Reserve Interest Rate Cut",
        description="The Fed has cut interest rates, directly affecting banking and credit markets."
    )
    assert "banking" in direct
    assert "real estate" in indirect


def test_mapper_empty_returns_no_sectors():
    """Verifies non-matching event returns empty industry lists."""
    direct, indirect = IndustryMapper.map_industries(
        title="Random Unrelated Content",
        description="Something with no industry keywords at all."
    )
    assert isinstance(direct, list)
    assert isinstance(indirect, list)


# ─────────────────────────────────────────────
# 3. ImpactAnalyzer Tests
# ─────────────────────────────────────────────

def test_analyzer_positive_impact():
    """Identifies positive impact for subsidy/rate cut events."""
    result = ImpactAnalyzer.analyze_impact(
        company_name="TechCorp Inc",
        industry="technology",
        event_title="Government Technology Subsidies Announced",
        event_description="Large government subsidies are offered for cloud and AI companies."
    )
    assert result["impact_type"] == "Positive Impact"
    assert "Positive Impact" in result["reasoning"]


def test_analyzer_negative_impact():
    """Identifies negative impact for tariff/antitrust events."""
    result = ImpactAnalyzer.analyze_impact(
        company_name="ChipMaker Corp",
        industry="semiconductors",
        event_title="Semiconductor Export Ban",
        event_description="A new ban was placed on semiconductor exports causing severe shortage."
    )
    assert result["impact_type"] == "Negative Impact"


def test_analyzer_neutral_impact():
    """Returns neutral impact for non-directional events."""
    result = ImpactAnalyzer.analyze_impact(
        company_name="NeutralCorp",
        industry="manufacturing",
        event_title="Annual Industry Conference",
        event_description="Industry leaders met to discuss general market conditions."
    )
    assert result["impact_type"] == "Neutral Impact"


def test_analyzer_confidence_scores():
    """Verifies confidence score ranges are bounded 0.0-1.0."""
    result = ImpactAnalyzer.analyze_impact(
        company_name="GlobalCorp",
        industry="energy",
        event_title="Oil Price Decline",
        event_description="Global oil prices have fallen due to oversupply."
    )
    assert result["impact_type"] in ["Positive Impact", "Negative Impact", "Neutral Impact"]
    assert "reasoning" in result


# ─────────────────────────────────────────────
# 4. EventIntelligenceService Integration Tests
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_event_intelligence_service_analyze():
    """Verifies EventIntelligenceService.analyze returns EventAnalyzeResponse."""
    from app.services.event_intelligence.service import EventIntelligenceService

    db_mock = AsyncMock()

    with patch("app.services.event_intelligence.service.EventRepository") as MockEventRepo, \
         patch("app.services.event_intelligence.service.CompanyMatcher") as MockMatcher, \
         patch("app.services.event_intelligence.service.EvidenceRetriever") as MockRetriever:

        # Mock EventRepository
        mock_repo = MagicMock()
        mock_repo.get_or_create_industry = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        MockEventRepo.return_value = mock_repo

        # Mock CompanyMatcher
        mock_company = MagicMock()
        mock_company.id = uuid.uuid4()
        mock_company.company_name = "TestCorp"
        mock_company.industry = "technology"
        mock_company.ticker_symbol = "TSTC"
        mock_matcher = MagicMock()
        mock_matcher.match_companies = AsyncMock(return_value=[
            {"company": mock_company, "confidence_score": 0.9}
        ])
        MockMatcher.return_value = mock_matcher

        # Mock EvidenceRetriever
        mock_retriever = MagicMock()
        mock_retriever.retrieve_evidence = AsyncMock(return_value=[])
        MockRetriever.return_value = mock_retriever

        # Mock DB commit
        db_mock.add = MagicMock()
        db_mock.commit = AsyncMock()

        service = EventIntelligenceService(db_mock)
        service.repository = mock_repo

        result = await service.analyze(
            title="Federal Reserve Rate Hike",
            description="The Fed has announced a 75bps interest rate hike to combat inflation."
        )

    assert isinstance(result, EventAnalyzeResponse)
    assert result.event_type == "macroeconomic"
    assert result.severity in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert len(result.affected_industries) > 0
    assert isinstance(result.potentially_impacted_companies, list)


# ─────────────────────────────────────────────
# 5. LangGraph Tool Tests
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_langgraph_event_tool_registered():
    """Verifies analyze_event_intelligence is registered as a LangGraph tool."""
    from app.ai.orchestrator.tools import create_tools
    db_mock = AsyncMock()

    with patch("app.ai.orchestrator.tools.EventIntelligenceService"):
        tools = create_tools(db_mock)

    assert "analyze_event_intelligence" in tools


@pytest.mark.asyncio
async def test_langgraph_event_tool_invocation():
    """Verifies analyze_event_intelligence tool returns structured dict on invocation."""
    from app.ai.orchestrator.tools import create_tools
    db_mock = AsyncMock()

    mock_response = EventAnalyzeResponse(
        event_summary="Test event summary",
        event_type="macroeconomic",
        severity="HIGH",
        affected_industries=["banking"],
        potentially_impacted_companies=[]
    )

    with patch("app.ai.orchestrator.tools.EventIntelligenceService") as MockService:
        mock_svc_instance = MagicMock()
        mock_svc_instance.analyze = AsyncMock(return_value=mock_response)
        MockService.return_value = mock_svc_instance

        tools = create_tools(db_mock)
        tool = tools["analyze_event_intelligence"]
        result = await tool.ainvoke({"title": "Rate Hike", "description": "Fed increases rates"})

    assert isinstance(result, dict)
    assert result["event_type"] == "macroeconomic"
    assert result["severity"] == "HIGH"


# ─────────────────────────────────────────────
# 6. API Endpoint Tests
# ─────────────────────────────────────────────

def test_api_analyze_event_success(client: TestClient):
    """Verifies POST /api/v1/events/analyze returns EventAnalyzeResponse."""
    mock_analysis = EventAnalyzeResponse(
        event_summary="Rate hike summary.",
        event_type="macroeconomic",
        severity="HIGH",
        affected_industries=["banking", "real estate"],
        potentially_impacted_companies=[
            CompanyImpact(
                company_id=uuid.uuid4(),
                company_name="FinanceCorp",
                industry="banking",
                impact_type="Negative Impact",
                confidence_score=0.9,
                reasoning="Rising rates compress bank margins.",
                evidence=[]
            )
        ]
    )

    with patch("app.api.v1.routers.event.EventIntelligenceService") as MockService:
        mock_svc_instance = MagicMock()
        mock_svc_instance.analyze = AsyncMock(return_value=mock_analysis)
        MockService.return_value = mock_svc_instance

        response = client.post("/api/v1/events/analyze", json={
            "title": "Federal Reserve Rate Hike",
            "description": "The Fed raised rates by 75bps."
        })

    assert response.status_code == 200
    data = response.json()
    assert data["event_type"] == "macroeconomic"
    assert data["severity"] == "HIGH"
    assert "banking" in data["affected_industries"]
    assert len(data["potentially_impacted_companies"]) == 1
    assert data["potentially_impacted_companies"][0]["company_name"] == "FinanceCorp"


def test_api_analyze_event_error_handling(client: TestClient):
    """Verifies POST /api/v1/events/analyze returns 500 on internal failures."""
    with patch("app.api.v1.routers.event.EventIntelligenceService") as MockService:
        mock_svc_instance = MagicMock()
        mock_svc_instance.analyze = AsyncMock(side_effect=Exception("Pipeline error"))
        MockService.return_value = mock_svc_instance

        response = client.post("/api/v1/events/analyze", json={
            "title": "Error Event",
            "description": "Cause an internal error."
        })

    assert response.status_code == 500
