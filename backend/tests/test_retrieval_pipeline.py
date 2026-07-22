import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from app.services.retrieval import is_substantive_chunk, RetrievalService
from app.models.document_chunk import DocumentChunk
from app.models.document import Document, DocumentType
from app.ai.orchestrator.tools import create_tools


def test_is_substantive_chunk():
    # Content chunk
    content = "Arvind Limited is a leading textile manufacturer in India, operating in retail and apparel brands."
    assert is_substantive_chunk(content) is True

    # Short chunk
    short = "Too short."
    assert is_substantive_chunk(short) is False

    # TOC chunk
    toc = "Table of Contents\nChairman's Message................... page 3\nFinancial Highlights.................. page 12\nRisks Factors......................... page 24"
    assert is_substantive_chunk(toc) is False

    # Index page with many dots
    index_page = "1. Introduction .. 2\n2. Operations .. 5\n3. Financial Statements .. 10\n4. Notes .. 20"
    assert is_substantive_chunk(index_page) is False


@pytest.mark.asyncio
async def test_search_similarity_zero_vector_fallback():
    # Setup mock DB session and matches
    db = AsyncMock()
    
    # Mock chunks
    doc = Document(id=uuid.uuid4(), title="Annual Report")
    chunk1 = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        chunk_text="Arvind Limited operates in the textile and retail industry.",
        company_id=uuid.uuid4(),
        page_number=5,
        chunk_index=0,
        document_type=DocumentType.annual_report,
        fiscal_year=2025,
        embedding=[0.0] * 1536
    )
    chunk1.document = doc
    
    chunk2 = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        chunk_text="Some other unrelated sentence about machinery.",
        company_id=chunk1.company_id,
        page_number=6,
        chunk_index=1,
        document_type=DocumentType.annual_report,
        fiscal_year=2025,
        embedding=[0.0] * 1536
    )
    chunk2.document = doc

    # Mock DB execution
    result_mock = MagicMock()
    result_mock.all.return_value = [(chunk1,), (chunk2,)]
    db.execute = AsyncMock(return_value=result_mock)

    # Initialize retrieval service
    service = RetrievalService(db)

    # Vector of all zeros triggers fallback keyword matching
    zero_vector = [0.0] * 1536
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(service.embeddings, "get_embedding", lambda x: zero_vector)
        
        # Search query matching chunk1 keywords
        results = await service.search(
            query="textile retail Arvind Limited",
            top_k=2,
            company_id=chunk1.company_id
        )

        assert len(results) == 2
        # Check that chunk1 is returned first due to higher keyword matches
        assert "textile and retail" in results[0].chunk_text
        assert results[0].similarity_score > results[1].similarity_score


@pytest.mark.asyncio
async def test_search_knowledge_dynamic_resolution():
    # Mock db and company repo
    db = AsyncMock()
    
    # Mock company
    company_id = uuid.uuid4()
    company_mock = MagicMock()
    company_mock.id = company_id
    company_mock.company_name = "Arvind Limited"
    company_mock.ticker_symbol = "ARVIND"

    # Setup tools factories mocks
    with pytest.MonkeyPatch.context() as mp:
        # Mock CompanyService and retrieval
        mp.setattr("app.services.company.CompanyRepository.get_by_ticker", AsyncMock(return_value=company_mock))
        mp.setattr("app.services.company.CompanyRepository.get_multi", AsyncMock(return_value=[company_mock]))
        
        # Mock search method of RetrievalService
        mock_search = AsyncMock(return_value=[])
        mp.setattr(RetrievalService, "search", mock_search)

        # Create tools
        tools = create_tools(db)
        search_knowledge_tool = tools["search_knowledge"]

        # Call with company name instead of UUID string
        await search_knowledge_tool.ainvoke({
            "query": "What does Arvind Limited do?",
            "company_id": "Arvind Limited"
        })

        # Verify search was called with resolved company UUID
        mock_search.assert_called_once()
        args, kwargs = mock_search.call_args
        assert kwargs.get("company_id") == company_id
