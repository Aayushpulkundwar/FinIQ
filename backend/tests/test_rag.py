import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime
from app.rag.cleaner import TextCleaner
from app.rag.chunker import DocumentChunker
from app.rag.embeddings import EmbeddingService
from app.rag.parsers.pdf import PDFParser
from app.rag.parsers.docx import DocxParser
from app.rag.parsers.pptx import PptxParser
from app.services.tasks import process_document
from app.models.document import Document, ProcessingStatus, UploadStatus, DocumentType
from app.models.document_chunk import DocumentChunk


def test_text_cleaner():
    """Verify cleaner collapses whitespaces, collapses newlines, strips margins."""
    raw = "  Hello \t World!  \n\n\n  New Paragraph \xa0 details.   "
    cleaned = TextCleaner.clean(raw)
    assert cleaned == "Hello World!\n\nNew Paragraph details."


def test_document_chunker():
    """Verify character-based chunking segments text with overlap and maps metadata."""
    pages = [
        {"text": "This is page one text content of document.", "page_number": 1},
        {"text": "Page two text content goes here.", "page_number": 2}
    ]
    doc_id = uuid4()
    company_id = uuid4()

    chunks = DocumentChunker.chunk_document(
        pages=pages,
        document_id=doc_id,
        company_id=company_id,
        document_type="annual_report",
        fiscal_year=2026,
        chunk_size=15,
        chunk_overlap=5
    )

    assert len(chunks) > 0
    # First chunk checks
    c1 = chunks[0]
    assert c1["document_id"] == doc_id
    assert "metadata" in c1
    assert c1["metadata"]["page_number"] == 1
    assert c1["metadata"]["chunk_index"] == 0
    assert c1["metadata"]["document_type"] == "annual_report"


@pytest.mark.asyncio
async def test_pdf_parser():
    """Verify PDFParser uses fitz to parse page text."""
    parser = PDFParser()
    mock_page = MagicMock()
    mock_page.get_text.return_value = "Extracted PDF Page Text"

    with patch("fitz.open") as mock_open:
        mock_doc = MagicMock()
        mock_doc.__iter__.return_value = [mock_page]
        mock_open.return_value = mock_doc

        result = parser.parse(b"dummy_bytes")
        assert len(result) == 1
        assert result[0]["text"] == "Extracted PDF Page Text"
        assert result[0]["page_number"] == 1


@pytest.mark.asyncio
async def test_docx_parser():
    """Verify DocxParser parses word documents logical paragraph grouping."""
    parser = DocxParser()
    mock_p = MagicMock()
    mock_p.text = "Docx Para Text"

    with patch("docx.Document") as mock_doc_init:
        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_p] * 20
        mock_doc_init.return_value = mock_doc

        result = parser.parse(b"dummy_bytes")
        assert len(result) == 2  # 15 paras per page, total 20 paras -> 2 pages
        assert "Docx Para Text" in result[0]["text"]


@pytest.mark.asyncio
async def test_pptx_parser():
    """Verify PptxParser extracts shape text slide-by-slide."""
    parser = PptxParser()
    mock_shape = MagicMock()
    mock_shape.text = "Slide Content"
    mock_slide = MagicMock()
    mock_slide.shapes = [mock_shape]

    with patch("app.rag.parsers.pptx.Presentation") as mock_pres_init:
        mock_pres = MagicMock()
        mock_pres.slides = [mock_slide]
        mock_pres_init.return_value = mock_pres

        result = parser.parse(b"dummy_bytes")
        assert len(result) == 1
        assert result[0]["text"] == "Slide Content"
        assert result[0]["page_number"] == 1


def test_embedding_service_bge_m3_mock():
    """Verify EmbeddingService queries Ollama REST API correctly with BGE-M3 model (1024-dim)."""
    with patch("app.rag.embeddings.settings") as mock_settings:
        mock_settings.EMBEDDING_PROVIDER = "ollama"
        mock_settings.EMBEDDING_MODEL = "bge-m3"
        mock_settings.OLLAMA_BASE_URL = "http://host.docker.internal:11434"
        
        from unittest.mock import MagicMock
        with patch("app.rag.embeddings.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            
            # Mock single embedding response — BGE-M3 produces 1024-dim vectors
            mock_client.post.return_value = MagicMock(
                status_code=200,
                json=lambda: {"embeddings": [[0.1] * 1024]}
            )
            
            service = EmbeddingService()
            emb = service.get_embedding("hello")
            assert len(emb) == 1024
            assert emb[0] == 0.1



@pytest.mark.asyncio
async def test_celery_process_document_pipeline():
    """Verify process_document pipeline runs full ingestion from download to database save."""
    doc_id = uuid4()
    company_id = uuid4()
    now = datetime.utcnow()

    # Document mock setup
    mock_doc = Document(
        id=doc_id,
        company_id=company_id,
        title="Ingestion Test",
        document_type=DocumentType.annual_report,
        fiscal_year=2026,
        quarter=None,
        file_name="report.pdf",
        file_path="documents/company/report.pdf",
        file_size=1024,
        mime_type="application/pdf",
        upload_status=UploadStatus.completed,
        processing_status=ProcessingStatus.pending,
        uploaded_at=now,
        created_at=now,
        updated_at=now,
    )

    # Mock storage, parser, and embeddings
    with patch("sqlalchemy.ext.asyncio.create_async_engine") as MockCreateEngine, \
         patch("sqlalchemy.ext.asyncio.async_sessionmaker") as MockSessionMaker, \
         patch("app.services.tasks.StorageService") as MockStorage, \
         patch("app.services.tasks.PDFParser") as MockPDFParser, \
         patch("app.services.tasks.EmbeddingService") as MockEmbedding:
 
        # Session setup
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        MockCreateEngine.return_value = mock_engine

        db_mock = AsyncMock()
        db_entered = AsyncMock()
        db_entered.add = MagicMock()
        db_mock.__aenter__.return_value = db_entered
        
        session_maker_mock = MagicMock()
        session_maker_mock.return_value = db_mock
        MockSessionMaker.return_value = session_maker_mock

        # DocumentRepository mock
        with patch("app.services.tasks.DocumentRepository") as MockDocRepo:
            doc_repo_instance = AsyncMock()
            doc_repo_instance.get.return_value = mock_doc
            MockDocRepo.return_value = doc_repo_instance

            # StorageService mock
            storage_instance = MagicMock()
            storage_instance.download_file.return_value = b"pdf_bytes"
            MockStorage.return_value = storage_instance

            # Parser mock
            parser_instance = MagicMock()
            parser_instance.parse.return_value = [{"text": "Page one content.", "page_number": 1}]
            MockPDFParser.return_value = parser_instance

            # Embeddings mock
            embed_instance = MagicMock()
            embed_instance.get_embeddings.return_value = [[0.1] * 1536]
            MockEmbedding.return_value = embed_instance

            # Run pipeline
            await process_document(str(doc_id))

            # Asserts
            assert mock_doc.processing_status == ProcessingStatus.completed
            db_entered.add.assert_called_once()  # DocumentChunk added
            db_entered.commit.assert_called()


def test_semantic_chunker_advanced_filters():
    """Verify semantic chunker filters junk, detects TOC/UI chrome, parses sections/segments, and merges page boundaries."""
    # 1. UI Chrome Vertical Navigation (avg words per line < 1.5)
    pages_chrome = [
        {"text": "NEXT\nNEXT\nNEXT\nNEXT\nNEXTNOW\nIntegrated Annual Report\n2024-25", "page_number": 1}
    ]
    chunks = DocumentChunker.chunk_document(
        pages=pages_chrome,
        document_id=uuid4(),
        company_id=uuid4(),
        document_type="annual_report",
        fiscal_year=2025,
    )
    # The chunk should be rejected as UI chrome vertical navigation
    assert len(chunks) == 0

    # 2. Table of Contents / Page indexes (>= 50% TOC patterns)
    pages_toc = [
        {"text": "About the Report 6\nFY25 Key Highlights 8\nChairman's Message 10\nAbout Arvind 14", "page_number": 1}
    ]
    chunks = DocumentChunker.chunk_document(
        pages=pages_toc,
        document_id=uuid4(),
        company_id=uuid4(),
        document_type="annual_report",
        fiscal_year=2025,
    )
    # The chunk should be rejected as TOC page index
    assert len(chunks) == 0

    # 3. Clean substantive text with segment/statement tags
    pages_clean = [
        {
            "text": "Arvind Limited Statement of Profit and Loss for the fiscal year ended March 31, 2025.\n\nRevenue from operations stood at 8000 Crores. Diluted EPS was 15.4.\n\nWe operate across our primary textiles business segment.",
            "page_number": 2,
            "section_title": "Financial Highlights"
        }
    ]
    chunks = DocumentChunker.chunk_document(
        pages=pages_clean,
        document_id=uuid4(),
        company_id=uuid4(),
        document_type="annual_report",
        fiscal_year=2025,
    )
    assert len(chunks) > 0
    meta = chunks[0]["metadata"]
    assert meta["section_title"] == "Financial Highlights"
    assert meta["statement_type"] == "income_statement"
    assert "textiles" in meta["business_segments"]

    # 4. Paragraph merging across page boundaries (ends in non-punctuation continues lowercase)
    pages_split = [
        {"text": "Arvind Limited is a leading textile manufacturer that operates in", "page_number": 1},
        {"text": "textiles and retail segments across India and global markets.", "page_number": 2}
    ]
    chunks = DocumentChunker.chunk_document(
        pages=pages_split,
        document_id=uuid4(),
        company_id=uuid4(),
        document_type="annual_report",
        fiscal_year=2025,
    )
    assert len(chunks) == 1
    assert "operates in textiles and retail" in chunks[0]["chunk_text"]


def test_financial_intelligence_engine():
    """Verify programmatic math calculations in FinancialIntelligenceEngine."""
    from app.services.financial_analysis import FinancialIntelligenceEngine
    
    # 1. DCF Valuation
    dcf = FinancialIntelligenceEngine.calculate_dcf(
        fcf=100.0,
        growth_rate=0.10,
        discount_rate=0.12,
        terminal_growth=0.03,
        periods=5
    )
    assert "enterprise_value" in dcf
    assert dcf["enterprise_value"] > 0
    assert len(dcf["projected_fcf"]) == 5

    # 2. YoY growth rates
    growth = FinancialIntelligenceEngine.calculate_yoy_growth([100.0, 120.0, 150.0])
    assert len(growth) == 2
    assert pytest.approx(growth[0], 0.01) == 0.20
    assert pytest.approx(growth[1], 0.01) == 0.25

    # 3. Margins
    margins = FinancialIntelligenceEngine.calculate_margins(revenue=1000.0, ebitda=300.0, net_profit=100.0)
    assert margins["ebitda_margin"] == 0.30
    assert margins["net_profit_margin"] == 0.10

    # 4. Scenario generation
    scenarios = FinancialIntelligenceEngine.generate_scenarios(base_fcf=100.0)
    assert "bull" in scenarios
    assert "base" in scenarios
    assert "bear" in scenarios
    assert scenarios["bull"]["enterprise_value"] > scenarios["base"]["enterprise_value"]
    assert scenarios["base"]["enterprise_value"] > scenarios["bear"]["enterprise_value"]

