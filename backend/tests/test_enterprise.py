import uuid
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.user import UserRole
from app.models.company import Company
from app.core.security import hash_password, create_access_token
from app.ai.evaluation import evaluate_hallucination, verify_citations, evaluate_retrieval_accuracy
from app.services.tasks import process_news
from app.core.circuit_breaker import get_circuit_breaker, CircuitState, CircuitBreakerError
from app.schemas.portfolio import PortfolioOut, PortfolioAnalysisResponse, PortfolioRecommendationResponse, WatchlistOut


# ── 1. AI Evaluation Framework Tests ─────────────────────────────────────────

def test_hallucination_evaluation():
    response = "The company reported Q3 revenue growth of 15% due to SaaS expansion."
    sources = [
        "Corporate Q3 report: SaaS expansion drove revenue growth up 15%.",
        "Our cloud enterprise systems expanded."
    ]
    score = evaluate_hallucination(response, sources)
    assert score > 0.5  # High keyword overlap

    # Test complete hallucination (no overlap)
    score_hallucinated = evaluate_hallucination("Gold prices reached record highs today.", sources)
    assert score_hallucinated < 0.2


def test_citation_verification():
    chunks = [
        {"document_title": "10-K", "page_number": 5},
        {"document_title": "Q3 Slides", "page_number": 12}
    ]
    # Valid citations
    assert verify_citations("As shown in [1] and [2], growth was solid.", chunks) is True
    # Invalid citation out of range
    assert verify_citations("As shown in [3], growth was solid.", chunks) is False


def test_retrieval_accuracy_precision():
    chunks = [
        {"similarity_score": 0.85},
        {"similarity_score": 0.72},
        {"similarity_score": 0.35} # lower than threshold
    ]
    # Accuracy at 0.5 threshold should be 2/3
    precision = evaluate_retrieval_accuracy("dummy query", chunks, similarity_threshold=0.5)
    assert precision == pytest.approx(0.6667, abs=1e-3)


# ── 2. Circuit Breaker Tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_circuit_breaker_flow():
    breaker = get_circuit_breaker("test_breaker", failure_threshold=2, recovery_timeout=0.1)
    
    async def mock_fail():
        raise ValueError("API error")
        
    async def mock_success():
        return "OK"

    # Consecutive failures trigger OPEN state
    with pytest.raises(ValueError):
        await breaker.call(mock_fail)
    with pytest.raises(ValueError):
        await breaker.call(mock_fail)
        
    assert breaker.state == CircuitState.OPEN

    # Open state blocks calls instantly
    with pytest.raises(CircuitBreakerError):
        await breaker.call(mock_success)

    # Wait cooling time
    import asyncio
    await asyncio.sleep(0.15)

    # Next call runs (HALF-OPEN) and success resets it to CLOSED
    res = await breaker.call(mock_success)
    assert res == "OK"
    assert breaker.state == CircuitState.CLOSED


# ── 3. Asynchronous News Ingestion Task Tests ─────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.tasks.NewsIntelligenceService")
@patch("app.services.tasks.MarketIntelligenceService")
async def test_async_news_ingestion(mock_market, mock_news):
    news_inst = mock_news.return_value
    news_inst.ingest_news = AsyncMock(return_value=[{"title": "Market Rally"}])
    
    market_inst = mock_market.return_value
    market_inst.analyze = AsyncMock()

    payload = {
        "title": "Fed raises interest rates",
        "content": "In a surprise policy shift the Federal Reserve raised rates.",
        "url": "https://financialnews.com/fed-rates",
        "source": "Financial News",
        "published_at": "2026-07-03T12:00:00Z",
        "summary": "Fed policy shift increases interest rates."
    }


    # Execute async news parser task
    await process_news(payload)

    # Verify news service ingestion is triggered
    assert news_inst.ingest_news.called is True
    assert market_inst.analyze.called is True


# ── 4. Observability Middleware Tests ────────────────────────────────────────

def test_observability_middleware_headers(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    # Observability middleware must generate request ID header
    assert "X-Request-ID" in response.headers


# ── 5. Enterprise Authentication & Portfolio CRUD Tests ────────────────────────

def test_user_auth_register_and_login(client: TestClient):
    email = "analyst-test@finsight.ai"
    reg_payload = {
        "email": email,
        "password": "secretpassword",
        "role": "analyst"
    }

    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()
    mock_user.email = email
    mock_user.role = UserRole.analyst
    mock_user.is_active = True

    # 1. Patch PortfolioRepository for Registration and Login
    with patch("app.api.v1.routers.auth.PortfolioRepository") as MockRepo:
        repo_instance = MockRepo.return_value
        repo_instance.get_user_by_email = AsyncMock(return_value=None)
        repo_instance.create_user = AsyncMock(return_value=mock_user)
        repo_instance.log_audit = AsyncMock()

        reg_response = client.post("/api/v1/auth/register", json=reg_payload)
        assert reg_response.status_code == 201
        assert reg_response.json()["email"] == email

    # 2. Patch login credentials validation
    with patch("app.api.v1.routers.auth.PortfolioRepository") as MockRepo:
        repo_instance = MockRepo.return_value
        repo_instance.get_user_by_email = AsyncMock(return_value=mock_user)
        repo_instance.log_audit = AsyncMock()

        with patch("app.api.v1.routers.auth.verify_password", return_value=True):
            login_response = client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "secretpassword"}
            )
            assert login_response.status_code == 200
            tokens = login_response.json()
            assert "access_token" in tokens
            assert "refresh_token" in tokens


def test_portfolio_operations(client: TestClient):
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, role="user")
    headers = {"Authorization": f"Bearer {token}"}

    portfolio_id = uuid.uuid4()
    company_id = uuid.uuid4()
    from datetime import datetime

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.role = UserRole.user
    mock_user.is_active = True

    mock_val_out = PortfolioOut(
        id=portfolio_id,
        name="Tech Growth Fund",
        user_id=user_id,
        holdings=[],
        total_market_value=15000.0,
        total_cost_basis=12000.0,
        total_gain_loss=3000.0,
        pnl_pct=25.0,
        created_at=datetime.utcnow()
    )

    mock_analysis = PortfolioAnalysisResponse(
        portfolio_id=portfolio_id,
        portfolio_name="Tech Growth Fund",
        total_market_value=15000.0,
        allocation_by_company=[],
        allocation_by_sector=[],
        risk_score=6.5,
        diversification_status="Well Diversified"
    )

    mock_recommendations = PortfolioRecommendationResponse(
        portfolio_id=portfolio_id,
        recommendations="AI generated rebalancing suggestions.",
        suggested_allocations=[]
    )

    # Patch user validation dependency
    with patch("app.core.security.PortfolioRepository") as MockSecRepo:
        sec_repo_inst = MockSecRepo.return_value
        sec_repo_inst.get_user = AsyncMock(return_value=mock_user)

        # Patch Portfolio Repository & PortfolioIntelligenceService
        with patch("app.api.v1.routers.portfolio.PortfolioRepository") as MockRepo, \
             patch("app.api.v1.routers.portfolio.PortfolioIntelligenceService") as MockSvc:
            
            repo_inst = MockRepo.return_value
            repo_inst.create_portfolio = AsyncMock(return_value=MagicMock(id=portfolio_id, name="Tech Growth Fund", user_id=user_id))
            repo_inst.get_portfolio = AsyncMock(return_value=MagicMock(user_id=user_id))
            repo_inst.add_holding = AsyncMock()
            repo_inst.log_audit = AsyncMock()


            svc_inst = MockSvc.return_value
            svc_inst.get_portfolio_valuation = AsyncMock(return_value=mock_val_out)
            svc_inst.analyze_portfolio = AsyncMock(return_value=mock_analysis)
            svc_inst.get_portfolio_recommendations = AsyncMock(return_value=mock_recommendations)
            svc_inst.repo.get_portfolio = AsyncMock(return_value=MagicMock(user_id=user_id))


            # Test 1: Create portfolio
            port_response = client.post(
                "/api/v1/portfolio",
                json={"name": "Tech Growth Fund"},
                headers=headers
            )
            assert port_response.status_code == 201
            assert port_response.json()["name"] == "Tech Growth Fund"

            # Test 2: Add holding
            hold_payload = {
                "company_id": str(company_id),
                "shares": 100,
                "average_cost": 150.0
            }

            hold_response = client.post(
                f"/api/v1/portfolio/{portfolio_id}/holdings",
                json=hold_payload,
                headers=headers
            )
            assert hold_response.status_code == 200

            # Test 3: Get analysis
            analysis_resp = client.get(f"/api/v1/portfolio/{portfolio_id}/analysis", headers=headers)
            assert analysis_resp.status_code == 200
            assert analysis_resp.json()["risk_score"] == 6.5

            # Test 4: Get recommendations
            recs_resp = client.get(f"/api/v1/portfolio/{portfolio_id}/recommendations", headers=headers)
            assert recs_resp.status_code == 200
            assert recs_resp.json()["recommendations"] == "AI generated rebalancing suggestions."


# ── 6. Multi-Agent Orchestrator LangGraph Routing Tests ────────────────────────

@pytest.mark.asyncio
async def test_multi_agent_orchestrator_routing():
    from app.ai.orchestrator.graph import supervisor_node
    
    state = {
        "user_query": "What is MSFT's valuation and free cash flow trend?",
        "planned_tools": [],
        "planned_agents": [],
        "execution_history": [],
        "retrieved_chunks": [],
        "company_details": None,
        "document_metadata": [],
        "final_context": {},
    }

    mock_routing_response = '[{"name": "calculate_company_valuation", "args": {"company_id": "__resolve_from_ticker__"}}]'
    with patch("app.core.openrouter_client.openrouter_chat", AsyncMock(return_value=mock_routing_response)):
        res = await supervisor_node(state, {})
    # Should schedule at least financial_statement or valuation agents
    assert "planned_agents" in res
    assert len(res["planned_agents"]) > 0
    # Must map to specialized agents
    assert "valuation" in res["planned_agents"] or "financial_statement" in res["planned_agents"]

