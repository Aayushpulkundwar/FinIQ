import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from app.ai.orchestrator.graph import supervisor_node, tool_execution_node, orchestrator_graph


@pytest.mark.asyncio
async def test_supervisor_node_routing_ticker():
    """Verify supervisor schedules get_company_by_ticker when query contains an uppercase ticker."""
    state = {
        "user_query": "What is the sector for MSFT?",
        "retrieved_chunks": [],
        "company_details": None,
        "document_metadata": [],
        "execution_history": [],
        "final_context": {},
        "planned_tools": []
    }

    # Force rule-based router path by patching config/settings
    with patch("app.ai.orchestrator.graph.settings") as mock_settings:
        mock_settings.OPENAI_API_KEY = "placeholder-key"

        result = await supervisor_node(state, config={})
        planned_names = [p["name"] for p in result["planned_tools"]]

        assert "get_company_by_ticker" in planned_names
        assert "search_knowledge" in planned_names


@pytest.mark.asyncio
async def test_supervisor_node_routing_documents():
    """Verify supervisor schedules list_documents when query asks about documents."""
    state = {
        "user_query": "Show me reports or documents for the company.",
        "retrieved_chunks": [],
        "company_details": None,
        "document_metadata": [],
        "execution_history": [],
        "final_context": {},
        "planned_tools": []
    }

    with patch("app.ai.orchestrator.graph.settings") as mock_settings:
        mock_settings.OPENAI_API_KEY = "placeholder-key"

        result = await supervisor_node(state, config={})
        planned_names = [p["name"] for p in result["planned_tools"]]

        assert "list_documents" in planned_names
        assert "search_knowledge" in planned_names


@pytest.mark.asyncio
async def test_tool_execution_node_flow():
    """Verify tool execution node executes tool list and aggregates context state."""
    state = {
        "user_query": "Query text",
        "retrieved_chunks": [],
        "company_details": None,
        "document_metadata": [],
        "execution_history": [],
        "final_context": {},
        "planned_tools": [
            {"name": "get_company_by_ticker", "args": {"ticker_symbol": "MSFT"}},
            {"name": "search_knowledge", "args": {"query": "Query text"}}
        ]
    }

    # Mock tool adapter objects exposing .ainvoke
    mock_company_tool = MagicMock()
    mock_company_tool.ainvoke = AsyncMock(return_value={"company_name": "Microsoft"})

    mock_retrieval_tool = MagicMock()
    mock_retrieval_tool.ainvoke = AsyncMock(return_value=[{"chunk_text": "Microsoft text chunk", "similarity_score": 0.9}])

    mock_tools = {
        "get_company_by_ticker": mock_company_tool,
        "search_knowledge": mock_retrieval_tool
    }

    with patch("app.ai.orchestrator.graph.create_tools", return_value=mock_tools):
        db_mock = AsyncMock()
        config = {"configurable": {"db": db_mock}}

        result = await tool_execution_node(state, config=config)

        assert result["company_details"] == {"company_name": "Microsoft"}
        assert len(result["retrieved_chunks"]) == 1
        assert "get_company_by_ticker" in result["execution_history"]
        assert "search_knowledge" in result["execution_history"]
        assert result["final_context"]["company_info"] == {"company_name": "Microsoft"}


@pytest.mark.asyncio
async def test_orchestrator_graph_end_to_end():
    """Verify orchestrator state graph runs START -> Supervisor -> Tool Execution -> END."""
    state_input = {
        "user_query": "Sector for TSLA reports",
        "retrieved_chunks": [],
        "company_details": None,
        "document_metadata": [],
        "execution_history": [],
        "final_context": {},
    }

    # Mock tool adapter objects exposing .ainvoke
    mock_company_tool = MagicMock()
    mock_company_tool.ainvoke = AsyncMock(return_value={"company_name": "Tesla"})

    mock_retrieval_tool = MagicMock()
    mock_retrieval_tool.ainvoke = AsyncMock(return_value=[])

    mock_doc_tool = MagicMock()
    mock_doc_tool.ainvoke = AsyncMock(return_value=[])

    mock_tools = {
        "get_company_by_ticker": mock_company_tool,
        "search_knowledge": mock_retrieval_tool,
        "list_documents": mock_doc_tool
    }

    with patch("app.ai.orchestrator.graph.settings") as mock_settings, \
         patch("app.ai.orchestrator.graph.create_tools", return_value=mock_tools):
        mock_settings.OPENAI_API_KEY = "placeholder-key"
        db_mock = AsyncMock()

        final_state = await orchestrator_graph.ainvoke(
            state_input,
            config={"configurable": {"db": db_mock}}
        )

        assert final_state["company_details"] == {"company_name": "Tesla"}
        assert "get_company_by_ticker" in final_state["execution_history"]
        assert "list_documents" in final_state["execution_history"]
        assert "search_knowledge" in final_state["execution_history"]


def test_api_chat_query_endpoint(client: TestClient):
    """Verify POST /api/v1/chat/query invokes graph and returns response format."""
    mock_result_state = {
        "user_query": "What is MSFT?",
        "retrieved_chunks": [{"chunk_text": "MSFT details"}],
        "company_details": {"company_name": "Microsoft Corp"},
        "document_metadata": [],
        "execution_history": ["get_company_by_ticker", "search_knowledge"],
        "final_context": {"summary": "Done"},
    }

    with patch("app.api.v1.routers.chat.orchestrator_graph") as MockGraph:
        MockGraph.ainvoke = AsyncMock(return_value=mock_result_state)

        response = client.post("/api/v1/chat/query", json={"query": "What is MSFT?"})
        assert response.status_code == 200
        data = response.json()

        assert data["user_query"] == "What is MSFT?"
        assert data["company_details"] == {"company_name": "Microsoft Corp"}
        assert len(data["retrieved_chunks"]) == 1
        assert "get_company_by_ticker" in data["execution_history"]
