import pytest
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.models.market import NewsCategory, NewsSentiment, MarketImpactLevel
from app.schemas.market import (
    NewsIngestionResponse, NewsArticleOut,
    MarketAnalyzeResponse, SentimentBreakdown
)
from app.services.news_intelligence import NewsIntelligenceService
from app.services.market_intelligence import MarketIntelligenceService


# ─────────────────────────────────────────────
# 1. NewsIntelligenceService Tests
# ─────────────────────────────────────────────

def test_news_classification_macroeconomic():
    """Classifies Fed policy and inflation news as macroeconomic."""
    service = NewsIntelligenceService(db=AsyncMock())
    cat, conf = service._classify_category(
        "Federal Reserve inflation rate hike and monetary policy changes"
    )
    assert cat == NewsCategory.macroeconomic
    assert conf > 0.4


def test_news_classification_regulatory():
    """Classifies SEC fines and litigation news as regulatory."""
    service = NewsIntelligenceService(db=AsyncMock())
    cat, conf = service._classify_category(
        "SEC filing fine and regulatory compliance lawsuit filed"
    )
    assert cat == NewsCategory.regulatory
    assert conf > 0.4


def test_news_classification_sentiment_positive():
    """Classifies strong earnings growth as positive sentiment."""
    service = NewsIntelligenceService(db=AsyncMock())
    sent = service._classify_sentiment("Record profits surge and earnings growth beat estimates")
    assert sent == NewsSentiment.positive


def test_news_classification_sentiment_negative():
    """Classifies weak decline as negative sentiment."""
    service = NewsIntelligenceService(db=AsyncMock())
    sent = service._classify_sentiment("Widespread decline and earnings drop Miss targets")
    assert sent == NewsSentiment.negative


def test_news_ticker_extraction():
    """Extracts valid uppercase tickers and ignores stop words."""
    service = NewsIntelligenceService(db=AsyncMock())
    tickers = service._extract_tickers("MSFT is growing while AAPL declines, but WHO is calling the FED?")
    assert "MSFT" in tickers
    assert "AAPL" in tickers
    assert "WHO" not in tickers
    assert "FED" not in tickers


def test_news_industry_extraction():
    """Matches industry keywords against text to extract sector name."""
    service = NewsIntelligenceService(db=AsyncMock())
    industries = service._extract_industries("New artificial intelligence software and AI cloud platforms")
    assert "Technology" in industries


@pytest.mark.asyncio
async def test_news_ingestion_duplicate():
    """Skips ingestion if article content_hash already exists."""
    db_mock = AsyncMock()
    service = NewsIntelligenceService(db_mock)
    
    # Mock repo to return an existing article
    mock_existing_article = MagicMock(
        id=uuid.uuid4(),
        title="Duplicate Headline",
        category=NewsCategory.geopolitical,
        sentiment=NewsSentiment.neutral,
        relevance_score=0.7,
        confidence_score=0.7,
    )
    service.repo.get_article_by_hash = AsyncMock(return_value=mock_existing_article)

    from app.schemas.market import NewsIngestionRequest
    payload = NewsIngestionRequest(
        title="Duplicate Headline",
        source="Reuters",
        published_at=datetime.utcnow(),
        summary="A summary."
    )

    response = await service.ingest(payload)
    assert response.is_duplicate is True
    assert response.article_id == mock_existing_article.id
    db_mock.commit.assert_not_called()


@pytest.mark.asyncio
async def test_news_ingestion_success():
    """Successfully ingests, classifies, extracts tickers, and commits a new article."""
    db_mock = AsyncMock()
    service = NewsIntelligenceService(db_mock)

    # Mock no existing duplicate
    service.repo.get_article_by_hash = AsyncMock(return_value=None)
    
    # Mock repository creates
    mock_article = MagicMock(id=uuid.uuid4(), title="MSFT Tech Earnings Beat")
    mock_article.category = NewsCategory.company_specific
    mock_article.sentiment = NewsSentiment.positive
    mock_article.relevance_score = 0.8
    mock_article.confidence_score = 0.8
    service.repo.create_article = AsyncMock(return_value=mock_article)
    service.repo.create_news_company = AsyncMock()
    service.repo.create_news_industry = AsyncMock()

    # Mock company lookup for ticker
    mock_company = MagicMock(id=uuid.uuid4(), company_name="Microsoft Corp")
    service.company_repo.get_by_ticker = AsyncMock(return_value=mock_company)

    from app.schemas.market import NewsIngestionRequest
    payload = NewsIngestionRequest(
        title="MSFT Tech Earnings Beat",
        source="Bloomberg",
        published_at=datetime.utcnow(),
        summary="Microsoft beats earnings estimates with AI growth."
    )

    response = await service.ingest(payload)
    assert response.is_duplicate is False
    assert response.title == "MSFT Tech Earnings Beat"
    assert response.category == "company_specific"
    assert response.sentiment == "positive"
    assert "Microsoft Corp" in response.extracted_companies
    assert "Technology" in response.extracted_industries
    db_mock.commit.assert_called_once()


# ─────────────────────────────────────────────
# 2. MarketIntelligenceService Tests
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_market_analyze_no_articles():
    """Returns fallback response if no articles are found."""
    db_mock = AsyncMock()
    service = MarketIntelligenceService(db_mock)
    service.repo.get_recent_articles = AsyncMock(return_value=[])
    # company_repo.get returns None since no company_id is passed
    service.company_repo.get = AsyncMock(return_value=None)

    # Patch the cache so a stale Redis entry can't cause a false cache-hit
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()
    mock_cache.hash_key = MagicMock(return_value="test-hash-no-articles")
    with patch("app.services.market_intelligence.cache", mock_cache, create=True), \
         patch("app.core.cache.cache", mock_cache):
        response = await service.analyze()

    assert "No news articles available" in response.market_summary
    assert response.sentiment_analysis.total == 0


@pytest.mark.asyncio
async def test_market_analyze_success():
    """Aggregates news, computes sentiment, and generates AI market summary."""
    db_mock = AsyncMock()
    service = MarketIntelligenceService(db_mock)

    # 1. Mock recent articles
    article1 = MagicMock(
        id=uuid.uuid4(),
        title="AI Growth Accelerates",
        source="TechCrunch",
        url=None,
        published_at=datetime.utcnow(),
        summary="Summary of AI growth.",
        category=NewsCategory.industry,
        sentiment=NewsSentiment.positive,
        relevance_score=0.9,
        confidence_score=0.8,
        company_mentions=[],
        industry_mentions=[],
        created_at=datetime.utcnow(),
    )
    article2 = MagicMock(
        id=uuid.uuid4(),
        title="Fed Raises Rates",
        source="WSJ",
        url=None,
        published_at=datetime.utcnow(),
        summary="Rates increase.",
        category=NewsCategory.macroeconomic,
        sentiment=NewsSentiment.negative,
        relevance_score=0.8,
        confidence_score=0.8,
        company_mentions=[],
        industry_mentions=[],
        created_at=datetime.utcnow(),
    )
    service.repo.get_recent_articles = AsyncMock(return_value=[article1, article2])

    # 2. Mock EventIntelligenceService analyze
    mock_event_response = MagicMock()
    mock_event_response.potentially_impacted_companies = []
    service.event_service.analyze = AsyncMock(return_value=mock_event_response)

    # 3. Mock ResponseGenerationService response
    mock_ai_response = MagicMock(
        executive_summary="AI market summary report details.",
        supporting_evidence=["Evidence 1"]
    )
    service.response_generator.generate_response = AsyncMock(return_value=mock_ai_response)

    # 4. Mock repo create_market_event
    service.repo.create_market_event = AsyncMock()

    response = await service.analyze()
    assert response.market_summary == "AI market summary report details."
    assert len(response.related_news) == 2
    assert response.sentiment_analysis.total == 2
    assert response.sentiment_analysis.positive_count == 1
    assert response.sentiment_analysis.negative_count == 1
    assert response.sentiment_analysis.neutral_count == 0
    assert response.sentiment_analysis.overall_sentiment in ["positive", "negative", "neutral"]


# ─────────────────────────────────────────────
# 3. LangGraph Tool Tests
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_langgraph_market_tool_registered():
    """Verifies analyze_market_intelligence is registered as a LangGraph tool."""
    from app.ai.orchestrator.tools import create_tools
    db_mock = AsyncMock()

    with patch("app.ai.orchestrator.tools.MarketIntelligenceService"):
        tools = create_tools(db_mock)

    assert "analyze_market_intelligence" in tools


@pytest.mark.asyncio
async def test_langgraph_market_tool_invocation():
    """Verifies analyze_market_intelligence tool returns structured dict on invocation."""
    from app.ai.orchestrator.tools import create_tools
    db_mock = AsyncMock()

    mock_response = MarketAnalyzeResponse(
        market_summary="Test market summary",
        related_news=[],
        related_events=[],
        impacted_companies=[],
        impacted_industries=[],
        sentiment_analysis=SentimentBreakdown(
            positive_count=0, negative_count=0, neutral_count=0,
            total=0, overall_sentiment="neutral",
            positive_pct=0.0, negative_pct=0.0, neutral_pct=0.0
        ),
        supporting_evidence=[]
    )

    with patch("app.ai.orchestrator.tools.MarketIntelligenceService") as MockService:
        mock_svc_instance = MagicMock()
        mock_svc_instance.analyze = AsyncMock(return_value=mock_response)
        MockService.return_value = mock_svc_instance

        tools = create_tools(db_mock)
        tool = tools["analyze_market_intelligence"]
        result = await tool.ainvoke({"limit": 5})

    assert isinstance(result, dict)
    assert result["market_summary"] == "Test market summary"


# ─────────────────────────────────────────────
# 4. API Router Tests
# ─────────────────────────────────────────────

def test_api_ingest_news_success(client: TestClient):
    """Verifies POST /api/v1/market/ingest succeeds."""
    mock_resp = NewsIngestionResponse(
        article_id=uuid.uuid4(),
        title="API Ingest Headline",
        category="macroeconomic",
        sentiment="neutral",
        relevance_score=0.6,
        confidence_score=0.6,
        extracted_companies=["Google"],
        extracted_industries=["Technology"],
        is_duplicate=False
    )

    with patch("app.api.v1.routers.market.NewsIntelligenceService") as MockService:
        mock_svc_instance = MagicMock()
        mock_svc_instance.ingest = AsyncMock(return_value=mock_resp)
        MockService.return_value = mock_svc_instance

        response = client.post("/api/v1/market/ingest", json={
            "title": "API Ingest Headline",
            "source": "Reuters",
            "published_at": "2026-07-03T10:00:00Z",
            "summary": "This is a summary of the headline."
        })

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "API Ingest Headline"
    assert data["category"] == "macroeconomic"
    assert "Google" in data["extracted_companies"]


def test_api_analyze_market_success(client: TestClient):
    """Verifies POST /api/v1/market/analyze succeeds."""
    mock_resp = MarketAnalyzeResponse(
        market_summary="API market summary.",
        related_news=[],
        related_events=[],
        impacted_companies=["Microsoft Corp"],
        impacted_industries=["Technology"],
        sentiment_analysis=SentimentBreakdown(
            positive_count=1, negative_count=0, neutral_count=0,
            total=1, overall_sentiment="positive",
            positive_pct=100.0, negative_pct=0.0, neutral_pct=0.0
        ),
        supporting_evidence=["Article evidence"]
    )

    with patch("app.api.v1.routers.market.MarketIntelligenceService") as MockService:
        mock_svc_instance = MagicMock()
        mock_svc_instance.analyze = AsyncMock(return_value=mock_resp)
        MockService.return_value = mock_svc_instance

        response = client.post("/api/v1/market/analyze", json={
            "limit": 10
        })

    assert response.status_code == 200
    data = response.json()
    assert data["market_summary"] == "API market summary."
    assert "Microsoft Corp" in data["impacted_companies"]
    assert data["sentiment_analysis"]["overall_sentiment"] == "positive"
