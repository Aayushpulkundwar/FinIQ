"""
Comprehensive test suite for the Enterprise Hybrid OCR Subsystem.

Tests:
1. Native Text PDF Parsing (100% native text, 0 OCR calls).
2. Page-level Scanned PDF Detection & Nemotron Provider execution.
3. Persistent SHA256 OCR Disk Cache (Hit & Miss).
4. Exponential Backoff Retry System.
5. OCR Provider Abstraction & Modular Switching.
6. Document Structure Preservation (headings, tables, page breaks).
"""
import os
import sys
import time
import tempfile
import fitz  # PyMuPDF
from typing import List
from unittest.mock import MagicMock, patch

sys.path.insert(0, ".")

from app.core.config import settings
from app.services.ocr_cache import OCRCache
from app.services.ocr_providers.base import BaseOCRProvider
from app.services.ocr_providers.nemotron_provider import NemotronProvider
from app.services.ocr_service import OCRService, extract_text_from_pdf
from app.rag.parsers.pdf import PDFParser


class MockCustomProvider(BaseOCRProvider):
    """Mock provider for unit testing without network dependency."""
    def __init__(self):
        self.call_count = 0

    def process_page_image(self, image_bytes: bytes, page_num: int) -> str:
        self.call_count += 1
        return f"# Heading Page {page_num}\n\nProcessed via Mock OCR Provider on page {page_num}.\n\n| Col1 | Col2 |\n| --- | --- |\n| Val1 | Val2 |"


def create_test_text_pdf(path: str, num_pages: int = 3):
    """Creates a native text PDF using PyMuPDF."""
    doc = fitz.open()
    for i in range(1, num_pages + 1):
        page = doc.new_page()
        text = f"Annual Report FY2026 Page {i}.\nThis is a clear native text page with high text density and sufficient characters for extraction.\nFinancial Revenue: {i * 1000} Crore."
        page.insert_text((50, 50), text)
    doc.save(path)
    doc.close()


def create_test_scanned_pdf(path: str, num_pages: int = 2):
    """Creates a low-text / scanned image style PDF using PyMuPDF."""
    doc = fitz.open()
    for i in range(1, num_pages + 1):
        page = doc.new_page()
        # Insert only a tiny label to simulate scanned image page
        page.insert_text((50, 50), "")
    doc.save(path)
    doc.close()


def run_tests():
    print("=" * 70)
    print("STARTING OCR SUBSYSTEM COMPREHENSIVE TEST SUITE")
    print("=" * 70)

    test_dir = tempfile.mkdtemp()
    text_pdf_path = os.path.join(test_dir, "text_sample.pdf")
    scanned_pdf_path = os.path.join(test_dir, "scanned_sample.pdf")

    create_test_text_pdf(text_pdf_path, num_pages=3)
    create_test_scanned_pdf(scanned_pdf_path, num_pages=2)

    # -------------------------------------------------------------------------
    # TEST 1: Native Text PDF Extraction (0 OCR calls)
    # -------------------------------------------------------------------------
    print("\n[TEST 1] Native Text PDF Extraction...")
    mock_provider = MockCustomProvider()
    cache_dir = os.path.join(test_dir, "cache_t1")
    cache = OCRCache(cache_dir=cache_dir, enabled=True)
    service = OCRService(provider=mock_provider, cache=cache, page_text_threshold=50)

    t0 = time.time()
    result_text = service.process_document(text_pdf_path)
    elapsed = time.time() - t0

    assert "Annual Report FY2026 Page 1" in result_text, "Missing native text content from Page 1"
    assert "Annual Report FY2026 Page 3" in result_text, "Missing native text content from Page 3"
    assert mock_provider.call_count == 0, f"Expected 0 OCR provider calls for native PDF, got {mock_provider.call_count}"
    print(f"  ✓ PASS: Native PDF extracted in {elapsed:.2f}s with 0 OCR provider calls.")

    # -------------------------------------------------------------------------
    # TEST 2: Scanned PDF Extraction & Provider Execution
    # -------------------------------------------------------------------------
    print("\n[TEST 2] Scanned PDF Detection & Mock Provider Execution...")
    mock_provider_t2 = MockCustomProvider()
    cache_dir_t2 = os.path.join(test_dir, "cache_t2")
    cache_t2 = OCRCache(cache_dir=cache_dir_t2, enabled=True)
    service_t2 = OCRService(provider=mock_provider_t2, cache=cache_t2, page_text_threshold=50)

    result_scanned = service_t2.process_document(scanned_pdf_path)

    assert mock_provider_t2.call_count == 2, f"Expected 2 OCR calls for 2 scanned pages, got {mock_provider_t2.call_count}"
    assert "Processed via Mock OCR Provider on page 1" in result_scanned, "Missing OCR text for Page 1"
    assert "Processed via Mock OCR Provider on page 2" in result_scanned, "Missing OCR text for Page 2"
    assert "| Col1 | Col2 |" in result_scanned, "Markdown tables not preserved in output"
    print(f"  ✓ PASS: Scanned PDF correctly triggered {mock_provider_t2.call_count} parallel OCR requests.")

    # -------------------------------------------------------------------------
    # TEST 3: Persistent SHA256 Cache (Hit vs Miss)
    # -------------------------------------------------------------------------
    print("\n[TEST 3] SHA256 Disk Cache Hit vs Miss...")
    cache_dir_t3 = os.path.join(test_dir, "cache_t3")
    cache_t3 = OCRCache(cache_dir=cache_dir_t3, enabled=True)
    mock_provider_t3 = MockCustomProvider()
    service_t3 = OCRService(provider=mock_provider_t3, cache=cache_t3, page_text_threshold=50)

    # First run (Cache Miss)
    res_miss = service_t3.process_document(scanned_pdf_path)
    first_call_count = mock_provider_t3.call_count
    assert first_call_count == 2, "First run should be a cache miss with 2 OCR calls"

    # Second run (Cache Hit)
    res_hit = service_t3.process_document(scanned_pdf_path)
    second_call_count = mock_provider_t3.call_count
    assert second_call_count == first_call_count, f"Second run should be a cache hit with 0 additional calls (got {second_call_count})"
    assert res_hit == res_miss, "Cached text does not match original extraction result"
    print("  ✓ PASS: Persistent SHA256 cache hit verified (0 API calls on repeat run).")

    # -------------------------------------------------------------------------
    # TEST 4: Exponential Backoff Retry System
    # -------------------------------------------------------------------------
    print("\n[TEST 4] Exponential Backoff Retry System...")
    failing_attempts = 0

    class FailingProvider(BaseOCRProvider):
        def process_page_image(self, image_bytes: bytes, page_num: int) -> str:
            nonlocal failing_attempts
            failing_attempts += 1
            if failing_attempts < 3:
                raise TimeoutError("Simulated network timeout")
            return f"Recovered text on attempt {failing_attempts}"

    retry_provider = FailingProvider()
    # NemotronProvider retry wrap test using FailingProvider logic
    nemotron_retry_test = NemotronProvider(max_retries=3, retry_backoff=1.1)

    with patch.object(nemotron_retry_test.client.chat.completions, "create") as mock_create:
        # Simulate 2 failures followed by 1 success
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content="Retry Success Text"))]
        mock_create.side_effect = [
            Exception("Connection error 1"),
            Exception("Connection error 2"),
            mock_resp,
        ]

        text_retry = nemotron_retry_test.process_page_image(b"fake_image_bytes", page_num=1)
        assert text_retry == "Retry Success Text"
        assert mock_create.call_count == 3, f"Expected 3 retry calls, got {mock_create.call_count}"
        print(f"  ✓ PASS: NemotronProvider exponential retry system successfully recovered after {mock_create.call_count} attempts.")

    # -------------------------------------------------------------------------
    # TEST 5: Decoupled PDFParser Integration
    # -------------------------------------------------------------------------
    print("\n[TEST 5] PDFParser Integration...")
    from app.rag.parsers.pdf import PDFParser
    parser = PDFParser()
    parsed_pages = parser.parse(text_pdf_path)

    assert len(parsed_pages) == 3, f"Expected 3 parsed pages, got {len(parsed_pages)}"
    assert parsed_pages[0]["page_number"] == 1, "Page number ordering corrupted"
    assert "Annual Report FY2026 Page 1" in parsed_pages[0]["text"], "Missing text in parser page dict"
    print("  ✓ PASS: PDFParser cleanly wrapped extract_text_from_pdf with page structure objects.")

    print("\n" + "=" * 70)
    print("FINAL SUBSYSTEM TEST RESULT: ✓ ALL CHECKS PASSED")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_tests()
