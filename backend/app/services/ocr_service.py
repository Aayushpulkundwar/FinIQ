import os
import re
import time
import fitz  # PyMuPDF
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Tuple
from loguru import logger

from app.core.config import settings
from app.services.ocr_cache import OCRCache
from app.services.ocr_providers.base import BaseOCRProvider
from app.services.ocr_providers.nemotron_provider import NemotronProvider


class OCRService:
    """
    Enterprise hybrid OCR subsystem orchestrator.
    Combines page-level native text extraction heuristics, persistent SHA256 disk caching,
    concurrent thread-pool OCR workers, and modular provider abstraction (NVIDIA Nemotron Parse v1.2).
    Scales to 1000+ page annual reports while minimizing API calls and processing cost.
    """
    def __init__(
        self,
        provider: Optional[BaseOCRProvider] = None,
        cache: Optional[OCRCache] = None,
        max_workers: Optional[int] = None,
        page_text_threshold: Optional[int] = None,
        image_dpi: Optional[int] = None,
    ):
        self.provider = provider or NemotronProvider()
        self.cache = cache or OCRCache()
        self.max_workers = max_workers if max_workers is not None else settings.OCR_MAX_CONCURRENT_REQUESTS
        self.page_text_threshold = (
            page_text_threshold if page_text_threshold is not None else settings.OCR_PAGE_TEXT_THRESHOLD
        )
        self.image_dpi = image_dpi if image_dpi is not None else settings.OCR_IMAGE_DPI

    def is_page_scanned(self, native_text: str) -> bool:
        """
        Multi-heuristic page classification:
        Evaluates text length and word count to determine whether embedded native text is sufficient.
        Returns True if page is classified as scanned/low-text, False if native text is sufficient.
        """
        clean_text = native_text.strip()
        text_length = len(clean_text)
        word_count = len(re.findall(r"\b\w+\b", clean_text))

        # Primary heuristic: text length and minimum word threshold
        if text_length < self.page_text_threshold or word_count < 10:
            return True
        return False

    def process_document(
        self,
        pdf_path: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> str:
        """
        Extracts text from a PDF file using hybrid page-level processing:
        1. Checks persistent SHA256 disk cache.
        2. Inspects PDF page by page.
        3. Uses native text for text pages; dispatches scanned pages to concurrent OCR workers.
        4. Preserves page order, structure, headings, paragraphs, and markdown tables.
        5. Saves output to disk cache and returns complete merged document text.
        """
        doc_name = os.path.basename(pdf_path)
        logger.info(f"INFO Document: {doc_name}")

        # 1. Check persistent SHA256 cache
        cached_text = self.cache.get(pdf_path)
        if cached_text is not None:
            logger.info(f"INFO OCR cache hit: True")
            return cached_text

        logger.info(f"INFO OCR cache hit: False")
        t_start = time.time()

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found at path: '{pdf_path}'")

        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        logger.info(f"INFO Total pages: {total_pages}")

        native_pages: List[Tuple[int, str]] = []
        scanned_tasks: List[Tuple[int, bytes]] = []

        # 2. Page-level native extraction & heuristic classification
        logger.info("INFO: Attempting native text extraction page-by-page...")
        for page_idx in range(total_pages):
            page_num = page_idx + 1
            page = doc[page_idx]
            native_text = page.get_text("text", sort=True).strip()

            if self.is_page_scanned(native_text):
                # Render high-resolution page image for OCR
                pixmap = page.get_pixmap(dpi=self.image_dpi)
                image_bytes = pixmap.tobytes("png")
                scanned_tasks.append((page_num, image_bytes))
            else:
                native_pages.append((page_num, native_text))

        doc.close()

        num_native = len(native_pages)
        num_ocr = len(scanned_tasks)
        logger.info(f"INFO Native pages: {num_native}")
        logger.info(f"INFO OCR pages: {num_ocr}")

        page_results: Dict[int, str] = {p_num: text for p_num, text in native_pages}

        # 3. Concurrent OCR execution for scanned pages
        if num_ocr > 0:
            logger.info(
                f"INFO: No embedded text detected on {num_ocr} pages. "
                f"Falling back to NVIDIA Nemotron OCR (max_workers={self.max_workers})..."
            )
            completed_ocr_count = 0

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_page = {
                    executor.submit(self.provider.process_page_image, img_bytes, p_num): p_num
                    for p_num, img_bytes in scanned_tasks
                }

                for future in as_completed(future_to_page):
                    p_num = future_to_page[future]
                    completed_ocr_count += 1
                    try:
                        ocr_text = future.result()
                        page_results[p_num] = ocr_text
                        logger.info(f"OCR Page {completed_ocr_count} / {num_ocr} (PDF Page {p_num}) completed.")

                        if progress_callback:
                            progress_callback(num_native + completed_ocr_count, total_pages)

                    except Exception as e:
                        logger.error(f"OCR processing failed for PDF Page {p_num}: {e}")
                        raise RuntimeError(f"OCR failed after multiple retries for page {p_num}: {e}") from e

            logger.info("INFO: OCR completed successfully.")
        else:
            logger.info("INFO: Native extraction successful across all pages.")

        # 4. Merge all pages maintaining strict page order
        logger.info("INFO: Continuing with document chunking & merging...")
        merged_blocks = []
        for p_num in range(1, total_pages + 1):
            text = page_results.get(p_num, "").strip()
            if text:
                merged_blocks.append(f"--- [Page {p_num}] ---\n{text}")

        final_document_text = "\n\n".join(merged_blocks)
        elapsed_sec = time.time() - t_start
        avg_latency = (elapsed_sec / total_pages) if total_pages > 0 else 0.0

        logger.info(f"INFO OCR completed in {elapsed_sec:.1f} seconds (Avg {avg_latency:.2f}s/page)")

        # 5. Save to disk cache
        self.cache.set(pdf_path, final_document_text)

        return final_document_text


# Global default service singleton
default_ocr_service = OCRService()


def extract_text_from_pdf(
    pdf_path: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    Core reusable entrypoint function for extracting text from any PDF document.
    Automatically decides whether OCR is needed page-by-page, uses disk caching,
    and returns full extracted document text regardless of whether the PDF was text-based or scanned.
    """
    return default_ocr_service.process_document(pdf_path, progress_callback=progress_callback)
