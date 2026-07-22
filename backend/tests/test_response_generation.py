import pytest
import sys
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from app.services.response_generation import ResponseGenerationService
from app.ai.prompts.research import INVESTMENT_RESEARCH_PROMPT
from app.schemas.response_generation import AIResponse


def test_prompt_template_formatting():
    """Verify INVESTMENT_RESEARCH_PROMPT renders input keys correctly."""
    messages = INVESTMENT_RESEARCH_PROMPT.format_messages(
        query="What is Microsoft's sector?",
        company_details="Microsoft, MSFT, Tech",
        document_metadata="[]",
        search_matches="Microsoft is in Technology sector."
    )
    assert len(messages) == 2
    assert "What is Microsoft's sector?" in messages[1].content
    assert "Microsoft, MSFT, Tech" in messages[1].content


@pytest.mark.asyncio
async def test_response_generation_mock_fallback():
    """Verify ResponseGenerationService mock fallback creates grounded structured responses."""
    with patch("app.core.config.settings.ALLOW_MOCK_LLM", True):
        service = ResponseGenerationService()
        assert service.is_placeholder is True

        company = {"company_name": "Tesla Inc", "ticker_symbol": "TSLA"}
        chunks = [
            {
                "chunk_text": "Tesla Model Y was the best selling car.",
                "document_title": "Tesla Annual Report 2026",
                "page_number": 5
            }
        ]

        response = await service.generate_response(
            user_query="What was the best selling car?",
            company_details=company,
            document_metadata=[],
            retrieved_chunks=chunks
        )

        assert isinstance(response, AIResponse)
        assert "Tesla Inc" in response.executive_summary
        assert "Tesla Annual Report 2026, Page 5" in response.sources[0]
        assert len(response.key_insights) == 1
        assert "Tesla Model Y" in response.key_insights[0]


@pytest.mark.asyncio
async def test_response_generation_empty_context():
    """Verify response generation handles empty context gracefully by returning helper info."""
    with patch("app.core.config.settings.ALLOW_MOCK_LLM", True):
        service = ResponseGenerationService()
        response = await service.generate_response(
            user_query="Non-existent query",
            company_details=None,
            document_metadata=[],
            retrieved_chunks=[]
        )
        assert isinstance(response, AIResponse)
        assert "details were not found" in response.executive_summary
        assert len(response.sources) == 0


def test_api_chat_query_with_response(client: TestClient):
    """Verify POST /api/v1/chat/query returns structured AIResponse values."""
    mock_result_state = {
        "user_query": "What is MSFT?",
        "retrieved_chunks": [{"chunk_text": "MSFT details", "document_title": "Doc", "page_number": 2}],
        "company_details": {"company_name": "Microsoft Corp"},
        "document_metadata": [],
        "execution_history": [],
        "final_context": {},
    }

    mock_ai_response = AIResponse(
        executive_summary="Summary of MSFT Corp.",
        key_insights=["Insight MSFT"],
        supporting_evidence=["Evidence MSFT"],
        risks_limitations=["None"],
        sources=["Doc, Page 2"]
    )

    with patch("app.api.v1.routers.chat.orchestrator_graph") as MockGraph, \
         patch("app.api.v1.routers.chat.ResponseGenerationService") as MockGenService:

        MockGraph.ainvoke = AsyncMock(return_value=mock_result_state)
        MockGenService.return_value.generate_response = AsyncMock(return_value=mock_ai_response)

        response = client.post("/api/v1/chat/query", json={"query": "What is MSFT?"})
        assert response.status_code == 200
        data = response.json()

        assert data["user_query"] == "What is MSFT?"
        assert data["response"]["executive_summary"] == "Summary of MSFT Corp."
        assert data["response"]["key_insights"] == ["Insight MSFT"]
        assert data["response"]["sources"] == ["Doc, Page 2"]


@pytest.mark.asyncio
async def test_response_generation_openrouter_success():
    """Verify ResponseGenerationService successfully calls OpenRouter and parses output."""
    mock_response = """
    {
        "executive_summary": "Tesla makes electric cars and energy products.",
        "key_insights": ["Pioneered modern EVs"],
        "supporting_evidence": ["Model 3 sales"],
        "risks_limitations": ["Production scaling"],
        "sources": ["Tesla Website"],
        "confidence_score": 0.95
    }
    """
    
    with patch("app.services.response_generation.openrouter_chat", AsyncMock(return_value=mock_response)), \
         patch("app.core.config.settings.ALLOW_MOCK_LLM", False), \
         patch("app.core.config.settings.OPENROUTER_API_KEY", "sk-valid-openrouter-key"):
        
        service = ResponseGenerationService()
        response = await service.generate_response(
            user_query="How does Tesla perform?",
            company_details=None,
            document_metadata=[],
            retrieved_chunks=[{"chunk_text": "Tesla EV details.", "document_title": "Tesla doc", "page_number": 1}]
        )
        
        assert isinstance(response, AIResponse)
        assert "Tesla makes electric cars" in response.executive_summary
        assert response.key_insights == ["Pioneered modern EVs"]
        assert response.confidence_score == 0.95
        assert response.is_degraded is False


@pytest.mark.asyncio
async def test_response_generation_openrouter_failure():
    """Verify ResponseGenerationService handles OpenRouter failure by returning degraded response with error_message."""
    with patch("app.services.response_generation.openrouter_chat", AsyncMock(side_effect=Exception("OpenRouter API Error: 502 Bad Gateway"))), \
         patch("app.core.config.settings.ALLOW_MOCK_LLM", False), \
         patch("app.core.config.settings.OPENROUTER_API_KEY", "sk-valid-openrouter-key"):
         
        service = ResponseGenerationService()
        response = await service.generate_response(
            user_query="How does Tesla perform?",
            company_details=None,
            document_metadata=[],
            retrieved_chunks=[{"chunk_text": "Tesla EV details.", "document_title": "Tesla doc", "page_number": 1}]
        )
        
        assert isinstance(response, AIResponse)
        assert response.is_degraded is True
        assert "OpenRouter API Error" in response.error_message
        assert response.executive_summary == "AI analysis is temporarily unavailable."
