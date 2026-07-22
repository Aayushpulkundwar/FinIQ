import pytest
from unittest.mock import MagicMock, patch
from app.schemas.response_generation import AIResponse


def test_ai_response_tabular_field():
    """Verify AIResponse schema supports and validates tabular_analysis field."""
    res = AIResponse(
        executive_summary="Summary of findings",
        key_insights=["Insight"],
        supporting_evidence=["Evidence"],
        risks_limitations=["None"],
        sources=["Doc, Page 1"],
        tabular_analysis="| Header 1 | Header 2 |\n|---|---|\n| Val 1 | Val 2 |",
        confidence_score=0.9
    )
    assert res.tabular_analysis == "| Header 1 | Header 2 |\n|---|---|\n| Val 1 | Val 2 |"


def test_pdf_parser_table_extraction():
    """Verify PDFParser uses fitz find_tables and converts to Markdown table."""
    mock_doc = MagicMock()
    mock_doc.get_toc.return_value = []
    
    mock_page = MagicMock()
    
    def mock_get_text(*args, **kwargs):
        if len(args) > 0 and args[0] == "blocks":
            return [
                (10.0, 10.0, 100.0, 100.0, "Normal text content.", 0, 0),
                (200.0, 200.0, 500.0, 500.0, "Revenue 1200.50 1500.00", 1, 0)
            ]
        return "Normal text content."
    
    mock_page.get_text.side_effect = mock_get_text
    
    # Mock find_tables, extract, and bbox
    mock_table = MagicMock()
    mock_table.extract.return_value = [
        ["Particulars", "FY24", "FY25"],
        ["Revenue", "1200.50", "1500.00"],
        ["Net Profit", "120.00", "150.00"]
    ]
    mock_table.bbox = (190.0, 190.0, 510.0, 510.0)
    mock_page.find_tables.return_value = [mock_table]
    
    mock_doc.__len__.return_value = 1
    mock_doc.__iter__.return_value = [mock_page]
    
    with patch("fitz.open", return_value=mock_doc):
        from app.rag.parsers.pdf import PDFParser
        parser = PDFParser()
        pages = parser.parse(b"dummy pdf bytes")
        
        assert len(pages) == 1
        text = pages[0]["text"]
        assert "Normal text content." in text
        # The raw text inside table bbox should be excluded
        assert "Revenue 1200.50 1500.00" not in text
        
        # Verify the markdown table is in tables list
        assert len(pages[0]["tables"]) == 1
        md_table = pages[0]["tables"][0]
        assert "| Particulars | FY24 | FY25 |" in md_table
        assert "| Revenue | 1200.50 | 1500.00 |" in md_table
        assert "| Net Profit | 120.00 | 150.00 |" in md_table


@pytest.mark.asyncio
async def test_fallback_table_reconstruction():
    """Verify fallback generator parses text lines with table patterns and builds a markdown table."""
    from app.services.response_generation import ResponseGenerationService
    
    chunks = [
        {
            "chunk_text": "Financial Summary:\nRevenue   FY24   FY25\nSales     1000   1200\nEBITDA     150    200\nPlain descriptive sentence explaining performance.",
            "document_title": "Annual Report 2025",
            "page_number": 1,
            "section_title": "Overview",
            "chunk_index": 2
        }
    ]
    
    service = ResponseGenerationService()
    
    # Ensure cache is mocked
    from unittest.mock import AsyncMock
    mock_set = AsyncMock()
    
    with patch("app.core.cache.cache.set", mock_set):
        res = await service._generate_fallback(
            user_query="Show financial metrics summary",
            company_details={"company_name": "Test Co", "ticker_symbol": "TCO"},
            retrieved_chunks=chunks,
            cache_key="test_fallback_table_reconstruction"
        )
        
        assert res.tabular_analysis is not None
        assert "| Revenue | FY24 | FY25 |" in res.tabular_analysis
        assert "| Sales | 1000 | 1200 |" in res.tabular_analysis
        assert "| EBITDA | 150 | 200 |" in res.tabular_analysis
        # Plain sentence should NOT be in the table
        assert "Plain descriptive" not in res.tabular_analysis
