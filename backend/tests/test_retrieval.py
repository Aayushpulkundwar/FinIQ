import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime
from fastapi.testclient import TestClient
from app.models.document import Document, DocumentType
from app.models.document_chunk import DocumentChunk
from app.services.retrieval import RetrievalService
from app.schemas.retrieval import RetrievalRequest


def test_api_retrieval_search_success(client: TestClient):
    """Verify POST /api/v1/retrieval/search returns matches correctly."""
    company_id = uuid4()
    doc_id = uuid4()
    chunk_id = uuid4()
    now = datetime.utcnow()

    # Define mock chunk
    mock_doc = Document(
        id=doc_id,
        title="Microsoft FY26 Q3 report",
        document_type=DocumentType.quarterly_report,
        fiscal_year=2026,
    )
    mock_chunk = DocumentChunk(
        id=chunk_id,
        document_id=doc_id,
        company_id=company_id,
        chunk_text="Microsoft Azure revenue growth was 30% this quarter.",
        embedding=[0.1] * 1536,
        page_number=12,
        chunk_index=3,
        document_type=DocumentType.quarterly_report,
        fiscal_year=2026,
        section_title="Financial Highlights",
        document=mock_doc,
    )

    with patch("app.api.v1.routers.retrieval.RetrievalService") as MockService:
        from app.schemas.retrieval import RetrievalResponse
        instance = MockService.return_value
        instance.search = AsyncMock(return_value=[
            RetrievalResponse(
                chunk_text=mock_chunk.chunk_text,
                similarity_score=0.88,
                document_id=mock_chunk.document_id,
                document_title="Microsoft FY26 Q3 report",
                company_id=mock_chunk.company_id,
                page_number=mock_chunk.page_number,
                chunk_index=mock_chunk.chunk_index,
                section_title=mock_chunk.section_title,
                document_type=mock_chunk.document_type,
                fiscal_year=mock_chunk.fiscal_year,
            )
        ])

        payload = {
            "query": "What was Microsoft Azure revenue growth?",
            "top_k": 3,
            "minimum_similarity": 0.75,
            "company_id": str(company_id),
            "document_type": "quarterly_report",
            "fiscal_year": 2026,
            "page_number": 12,
        }

        response = client.post("/api/v1/retrieval/search", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["chunk_text"] == mock_chunk.chunk_text
        assert data[0]["similarity_score"] == 0.88
        assert data[0]["document_title"] == "Microsoft FY26 Q3 report"


def test_api_retrieval_search_empty(client: TestClient):
    """Verify search returns empty list when no matches exist instead of throwing."""
    with patch("app.api.v1.routers.retrieval.RetrievalService") as MockService:
        instance = MockService.return_value
        instance.search = AsyncMock(return_value=[])

        payload = {"query": "Non-existent terms"}
        response = client.post("/api/v1/retrieval/search", json=payload)
        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.asyncio
async def test_retrieval_service_orchestration():
    """Verify RetrievalService encodes query and invokes repository search."""
    db_mock = AsyncMock()
    service = RetrievalService(db_mock)

    company_id = uuid4()
    doc_id = uuid4()
    chunk_id = uuid4()

    mock_doc = Document(
        id=doc_id,
        title="Test report",
        document_type=DocumentType.annual_report,
        fiscal_year=2026,
    )
    mock_chunk = DocumentChunk(
        id=chunk_id,
        document_id=doc_id,
        company_id=company_id,
        chunk_text="Test chunk text",
        embedding=[0.0] * 1536,
        page_number=5,
        chunk_index=1,
        document_type=DocumentType.annual_report,
        fiscal_year=2026,
        section_title="Introduction",
        document=mock_doc,
    )

    # Mock repository
    service.repository = AsyncMock()
    service.repository.search_similarity.return_value = [(mock_chunk, 0.9)]

    # Mock embeddings
    service.embeddings = MagicMock()
    service.embeddings.get_embedding.return_value = [0.0] * 1536

    results = await service.search(
        query="test query",
        top_k=5,
        min_similarity=0.8,
        company_id=company_id,
    )

    assert len(results) == 1
    assert results[0].chunk_text == "Test chunk text"
    assert results[0].similarity_score == 0.9
    assert results[0].document_title == "Test report"

    service.embeddings.get_embedding.assert_called_once_with("test query")
    service.repository.search_similarity.assert_called_once()


@pytest.mark.asyncio
async def test_repository_search_similarity_clauses():
    """Verify repository builds query clauses and executes matching pgvector operations."""
    db_mock = AsyncMock()
    # Mock return value from executing the query statement
    mock_row = MagicMock()
    mock_chunk = MagicMock()
    mock_row.__getitem__.side_effect = lambda x: mock_chunk if x == 0 else 0.85

    mock_exec = MagicMock()
    mock_exec.all.return_value = [mock_row]
    db_mock.execute = AsyncMock(return_value=mock_exec)

    from app.repositories.document_chunk import DocumentChunkRepository
    repo = DocumentChunkRepository(db_mock)

    query_vector = [0.1] * 1536
    company_id = uuid4()

    result = await repo.search_similarity(
        query_embedding=query_vector,
        top_k=10,
        min_similarity=0.7,
        company_id=company_id,
        document_type=DocumentType.annual_report,
        fiscal_year=2026,
        page_number=2,
    )

    assert len(result) == 1
    assert result[0][0] == mock_chunk
    assert result[0][1] == 0.85
    db_mock.execute.assert_called_once()
