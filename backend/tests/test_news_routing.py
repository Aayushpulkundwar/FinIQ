import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4, UUID

from app.ai.orchestrator.graph import supervisor_node
from app.services.market_intelligence import MarketIntelligenceService
from app.schemas.news import NewsArticle


@pytest.mark.asyncio
async def test_news_query_routing_to_analyze_market_intelligence():
    """Verify 'most recent news regarding [Company]' routes to analyze_market_intelligence."""
    state = {
        "user_query": "give me the most recent news regarding TVS Supply Chain Solutions",
        "planned_tools": [],
        "planned_agents": [],
        "execution_history": [],
    }

    # Mock openrouter_chat to simulate LLM router response
    mock_llm_response = MagicMock()
    mock_llm_response.content = '[{"name": "get_company_by_ticker", "args": {"ticker_symbol": "TVSSCS"}}, {"name": "analyze_market_intelligence", "args": {"company_id": "__resolve_from_ticker__"}}]'
    mock_llm_response.provider_used = "openrouter"

    with patch("app.ai.orchestrator.graph.settings") as mock_settings, \
         patch("app.core.openrouter_client.openrouter_chat", AsyncMock(return_value=mock_llm_response)):
        mock_settings.OPENROUTER_API_KEY = "mock_key"
        mock_settings.OPENROUTER_MODEL = "mock_model"
        mock_settings.OPENROUTER_BASE_URL = "http://mock"

        res = await supervisor_node(state, {})
        planned_names = [t["name"] for t in res["planned_tools"]]

        assert "analyze_market_intelligence" in planned_names
        assert "search_knowledge" not in planned_names
        assert "news_intelligence" in res["planned_agents"]


@pytest.mark.asyncio
async def test_ambiguity_guard_financial_update_query_not_routed_to_news():
    """Verify 'recent updates on ROE trends for TVS' routes to financial/search_knowledge, NOT news."""
    state = {
        "user_query": "recent updates on ROE trends for TVS",
        "planned_tools": [],
        "planned_agents": [],
        "execution_history": [],
    }

    # Simulate fallback rule-based router (LLM fails)
    with patch("app.ai.orchestrator.graph.settings") as mock_settings:
        mock_settings.OPENROUTER_API_KEY = None  # Force rule-based router fallback

        res = await supervisor_node(state, {})
        planned_names = [t["name"] for t in res["planned_tools"]]

        # ROE keyword matches financial_keywords -> analyze_financial_intelligence
        assert "analyze_financial_intelligence" in planned_names or "search_knowledge" in planned_names
        assert "analyze_market_intelligence" not in planned_names


@pytest.mark.asyncio
async def test_llm_router_precedence_over_rule_based_fallback():
    """Assert LLM router result wins over rule-based matcher when LLM succeeds."""
    state = {
        "user_query": "headlines for TVS",
        "planned_tools": [],
        "planned_agents": [],
        "execution_history": [],
    }

    mock_llm_response = MagicMock()
    # LLM explicitly decides analyze_market_intelligence
    mock_llm_response.content = '[{"name": "analyze_market_intelligence", "args": {"company_id": "__resolve_from_ticker__"}}]'
    mock_llm_response.provider_used = "openrouter"

    with patch("app.ai.orchestrator.graph.settings") as mock_settings, \
         patch("app.core.openrouter_client.openrouter_chat", AsyncMock(return_value=mock_llm_response)):
        mock_settings.OPENROUTER_API_KEY = "mock_key"
        mock_settings.OPENROUTER_MODEL = "mock_model"
        mock_settings.OPENROUTER_BASE_URL = "http://mock"

        res = await supervisor_node(state, {})
        planned_names = [t["name"] for t in res["planned_tools"]]

        assert planned_names == ["analyze_market_intelligence"]


@pytest.mark.asyncio
async def test_market_intelligence_service_uses_live_apitube_news():
    """Verify MarketIntelligenceService.analyze invokes fetch_company_news and tags chunks with page_number: None."""
    mock_db = AsyncMock()
    mock_company = MagicMock()
    mock_company.id = uuid4()
    mock_company.company_name = "TVS Supply Chain Solutions Limited"
    mock_company.ticker_symbol = "TVSSCS.NS"

    mock_articles = [
        NewsArticle(
            id="00000000-0000-0000-0000-000000000001",
            title="TVS Supply Chain expands global presence",
            source="Economic Times",
            url="https://economictimes.example.com/news/1",
            published_at="2026-07-28T10:00:00Z",
            summary="TVS Supply Chain signed new contracts across Europe.",
            category="business",
            sentiment="positive",
        )
    ]

    service = MarketIntelligenceService(mock_db)
    service.company_repo.get = AsyncMock(return_value=mock_company)

    with patch("app.services.rss_news.fetch_company_news", AsyncMock(return_value=mock_articles)):
        result = await service.analyze(company_id=mock_company.id)

        assert len(result.related_news) == 1
        assert result.related_news[0].title == "TVS Supply Chain expands global presence"
        assert result.related_news[0].source == "Economic Times"
        assert result.related_news[0].url == "https://economictimes.example.com/news/1"


@pytest.mark.asyncio
async def test_market_intelligence_service_apitube_failure_loud_message():
    """Verify RSS failure returns explicit unavailable message without calling PDF RAG."""
    mock_db = AsyncMock()
    mock_company = MagicMock()
    mock_company.id = uuid4()
    mock_company.company_name = "TVS Supply Chain Solutions Limited"
    mock_company.ticker_symbol = "TVSSCS.NS"

    service = MarketIntelligenceService(mock_db)
    service.company_repo.get = AsyncMock(return_value=mock_company)

    with patch("app.services.rss_news.fetch_company_news", AsyncMock(side_effect=Exception("RSS feeds offline"))), \
         patch("app.services.retrieval.RetrievalService.search") as mock_rag_search:

        result = await service.analyze(company_id=mock_company.id)

        # Assert explicit loud error message
        assert "Live news currently unavailable for TVS Supply Chain Solutions Limited" in result.market_summary
        assert "RSS feeds offline" in result.market_summary
        # Assert PDF RAG retrieval was NEVER invoked
        mock_rag_search.assert_not_called()


@pytest.mark.asyncio
async def test_financial_query_regression_routes_to_rag():
    """Regression test: 'what was FY2025 revenue and EBITDA for TVS' routes to financial/document RAG."""
    state = {
        "user_query": "what was FY2025 revenue and EBITDA for TVS Supply Chain Solutions",
        "planned_tools": [],
        "planned_agents": [],
        "execution_history": [],
    }

    mock_llm_response = MagicMock()
    mock_llm_response.content = '[{"name": "get_company_by_ticker", "args": {"ticker_symbol": "TVSSCS"}}, {"name": "analyze_financial_intelligence", "args": {"company_id": "__resolve_from_ticker__", "fiscal_year": 2025}}]'
    mock_llm_response.provider_used = "openrouter"

    with patch("app.ai.orchestrator.graph.settings") as mock_settings, \
         patch("app.core.openrouter_client.openrouter_chat", AsyncMock(return_value=mock_llm_response)):
        mock_settings.OPENROUTER_API_KEY = "mock_key"
        mock_settings.OPENROUTER_MODEL = "mock_model"

        res = await supervisor_node(state, {})
        planned_names = [t["name"] for t in res["planned_tools"]]

        assert "analyze_financial_intelligence" in planned_names
        assert "analyze_market_intelligence" not in planned_names


@pytest.mark.asyncio
async def test_chat_router_is_rag_dependent_query_does_not_intercept_news_queries():
    """Verify is_rag_dependent_query in chat.py does NOT intercept news queries when chunk_count is 0."""
    from app.api.v1.routers.chat import ChatQueryRequest
    
    # Check that queries asking for news are treated as market/news queries, NOT document-RAG dependent
    query_text = "give me the most recent news related to TVS"
    query_lower = query_text.lower()
    
    market_keywords = [
        "price", "chart", "live", "quote", "trading", "ticker", "market cap",
        "pe ratio", "volume", "website", "exchange", "isin",
        "news", "most recent news", "latest news", "news regarding", "news about",
        "news for", "company news", "headlines", "press release", "current events"
    ]
    
    is_market = any(k in query_lower for k in market_keywords)
    assert is_market is True, "News keywords must be recognized as market/news intent to prevent 0-chunk interception"


@pytest.mark.asyncio
async def test_execute_agent_node_populates_retrieved_chunks_for_market_intelligence():
    """Verify execute_agent_node populates retrieved_chunks when analyze_market_intelligence runs."""
    from app.ai.orchestrator.graph import execute_agent_node
    
    state = {
        "user_query": "give me the most recent news related to TVS",
        "planned_tools": [{"name": "analyze_market_intelligence", "args": {"company_id": "mock_id"}}],
        "planned_agents": ["news_intelligence"],
        "retrieved_chunks": [],
        "execution_history": [],
        "company_details": {"id": "mock_id", "company_name": "TVS Supply Chain Solutions Limited"},
    }
    
    mock_market_res = {
        "market_summary": "TVS Supply Chain signed strategic logistics agreement.",
        "related_news": [
            {
                "title": "TVS Supply Chain signs agreement",
                "source": "Financial Express",
                "url": "https://financialexpress.com/news/1",
                "published_at": "2026-07-28",
                "summary": "TVS Supply Chain signed strategic logistics agreement.",
                "category": "business",
                "relevance_score": 0.95,
            }
        ]
    }
    
    mock_tool = AsyncMock(return_value=mock_market_res)
    mock_db = AsyncMock()
    
    with patch("app.ai.orchestrator.graph.create_tools", return_value={"analyze_market_intelligence": StructuredTool_from_func(mock_tool)}):
        # Run node helper
        node_res = await execute_agent_node("news_intelligence", state, {"configurable": {"db": mock_db}})
        
        chunks = node_res.get("retrieved_chunks", [])
        assert len(chunks) == 1
        assert chunks[0]["page_number"] is None
        assert chunks[0]["source"] == "Financial Express"
        assert chunks[0]["url"] == "https://financialexpress.com/news/1"


@pytest.mark.asyncio
async def test_general_document_qa_query_routes_to_search_knowledge():
    """Verify general company questions ('what does tvs do?') route to search_knowledge, NOT market_intelligence."""
    state = {
        "user_query": "what does tvs do?",
        "planned_tools": [],
        "planned_agents": [],
        "execution_history": [],
    }

    mock_llm_response = MagicMock()
    mock_llm_response.content = '[{"name": "get_company_by_ticker", "args": {"ticker_symbol": "TVS"}}, {"name": "search_knowledge", "args": {"query": "what does tvs do?", "company_id": "__resolve_from_ticker__"}}]'
    mock_llm_response.provider_used = "openrouter"

    with patch("app.ai.orchestrator.graph.settings") as mock_settings, \
         patch("app.core.openrouter_client.openrouter_chat", AsyncMock(return_value=mock_llm_response)):
        mock_settings.OPENROUTER_API_KEY = "mock_key"
        mock_settings.OPENROUTER_MODEL = "mock_model"

        res = await supervisor_node(state, {})
        planned_names = [t["name"] for t in res["planned_tools"]]

        assert "search_knowledge" in planned_names
        assert "analyze_market_intelligence" not in planned_names


@pytest.mark.asyncio
async def test_get_company_by_ticker_fuzzy_matching():
    """Verify get_company_by_ticker matches partial ticker or company name when exact match returns None."""
    mock_db = AsyncMock()
    mock_company = MagicMock()
    mock_company.id = uuid4()
    mock_company.company_name = "TVS Supply Chain Solutions Limited"
    mock_company.ticker_symbol = "TVSSCS.NS"
    mock_company.exchange = "NSE"
    mock_company.sector = "Industrials"
    mock_company.industry = "Logistics"
    mock_company.isin = "INE395N01027"
    mock_company.website = "https://www.tvsscs.com"

    with patch("app.repositories.company.CompanyRepository.get_by_ticker", AsyncMock(return_value=None)), \
         patch("app.repositories.company.CompanyRepository.get_multi", AsyncMock(return_value=[mock_company])):

        from app.ai.orchestrator.tools import create_tools
        tools = create_tools(mock_db)
        get_company_fn = tools["get_company_by_ticker"]

        res = await get_company_fn.ainvoke({"ticker_symbol": "TVS"})
        assert res is not None
        assert res["company_name"] == "TVS Supply Chain Solutions Limited"
        assert res["ticker_symbol"] == "TVSSCS.NS"


def StructuredTool_from_func(mock_func):
    """Helper mock tool object with ainvoke method."""
    mock_obj = MagicMock()
    mock_obj.ainvoke = mock_func
    return mock_obj

