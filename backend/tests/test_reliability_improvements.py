import pytest
import sys
import time
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.valuation_utils import clamp_wacc, clamp_growth_rate
from app.services.retrieval import RetrievalService
from app.schemas.retrieval import RetrievalResponse


def test_dcf_wacc_clamp():
    """Verify WACC clamps to typical boundaries of 6%-15% and returns clamp status."""
    # Within bounds (no clamp)
    clamped, was_clamped = clamp_wacc(0.10)
    assert clamped == 0.10
    assert was_clamped is False
    
    # Under bottom bound (clamped to 6%)
    clamped, was_clamped = clamp_wacc(0.0477)
    assert clamped == 0.06
    assert was_clamped is True
    
    # Over top bound (clamped to 15%)
    clamped, was_clamped = clamp_wacc(0.18)
    assert clamped == 0.15
    assert was_clamped is True


def test_dcf_growth_rate_clamp():
    """Verify FCF growth rate clamps to -15% to +25% boundaries and logs correctly."""
    # Within bounds (no clamp)
    clamped, was_clamped = clamp_growth_rate(0.08, source="analyst estimate")
    assert clamped == 0.08
    assert was_clamped is False
    
    # Under bottom bound (clamped to -15%)
    clamped, was_clamped = clamp_growth_rate(-0.25, source="historical FCF CAGR")
    assert clamped == -0.15
    assert was_clamped is True
    
    # Over top bound (clamped to 25%)
    clamped, was_clamped = clamp_growth_rate(0.35, source="historical revenue CAGR")
    assert clamped == 0.25
    assert was_clamped is True


@pytest.mark.asyncio
async def test_retrieval_keyword_fallback():
    """Verify search() falls back to keyword-only queries when embeddings fail, logging a CRITICAL failure."""
    # Mock embeddings to raise quota exception
    mock_embeddings = MagicMock()
    mock_embeddings.get_embedding.side_effect = Exception("insufficient_quota: billing limit exceeded")
    
    # Prepare dummy keyword matches
    import uuid
    dummy_chunk = MagicMock()
    dummy_chunk.id = uuid.uuid4()
    dummy_chunk.document_id = uuid.uuid4()
    dummy_chunk.company_id = uuid.uuid4()
    dummy_chunk.chunk_text = "Arvind is a premium textile manufacturer."
    dummy_chunk.section_title = "Business Overview"
    dummy_chunk.document_type = "annual_report"
    dummy_chunk.fiscal_year = 2025
    dummy_chunk.page_number = 12
    dummy_chunk.chunk_index = 3
    dummy_chunk.metadata_json = {"statement_type": None}
    
    mock_doc = MagicMock()
    mock_doc.title = "Arvind Limited IAR 2025"
    mock_company = MagicMock()
    mock_company.ticker_symbol = "ARVIND"
    mock_doc.company = mock_company
    dummy_chunk.document = mock_doc
    
    # Initialize RetrievalService with mocked dependencies
    with patch("app.core.config.settings.ALLOW_MOCK_LLM", True), \
         patch("app.core.config.settings.OPENROUTER_API_KEY", ""):
        
        service = RetrievalService(db=MagicMock())
        service.repository.db = object()
        service.embeddings = mock_embeddings
        
        # Mock repository methods on the real instance to bypass short circuit but return expected data
        service.repository.search_similarity = AsyncMock(return_value=[])
        service.repository.search_keyword = AsyncMock(return_value=[(dummy_chunk, 0.85)])
        
        # Trigger search
        results = await service.search(
            query="What does Arvind do?",
            company_id=None,
            top_k=2
        )
        
        # Verify keyword matches were returned despite embedding raising exception
        assert len(results) == 1
        assert results[0].chunk_text == "Arvind is a premium textile manufacturer."
        assert results[0].document_title == "Arvind Limited IAR 2025"
        
        # Assert keyword search repository method was called
        service.repository.search_keyword.assert_called()


def test_clamp_wacc_with_beta_check():
    """Verify clamp_wacc_with_beta_check returns correct flags."""
    from app.services.valuation_utils import clamp_wacc_with_beta_check
    
    # 1. No clamp
    clamped, was_clamped, was_clamped_fb = clamp_wacc_with_beta_check(0.10, "yfinance_valid")
    assert clamped == 0.10
    assert was_clamped is False
    assert was_clamped_fb is False
    
    # 2. Clamped, yfinance_valid (no fallback beta)
    clamped, was_clamped, was_clamped_fb = clamp_wacc_with_beta_check(0.04, "yfinance_valid")
    assert clamped == 0.06
    assert was_clamped is True
    assert was_clamped_fb is False
    
    # 3. Clamped, due to fallback beta
    clamped, was_clamped, was_clamped_fb = clamp_wacc_with_beta_check(0.04, "fallback_invalid_range")
    assert clamped == 0.06
    assert was_clamped is True
    assert was_clamped_fb is True
    
    # 4. No clamp, but fallback beta present
    clamped, was_clamped, was_clamped_fb = clamp_wacc_with_beta_check(0.09, "fallback_invalid_range")
    assert clamped == 0.09
    assert was_clamped is False
    assert was_clamped_fb is False
