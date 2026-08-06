import os
import re
import tempfile
from typing import Any, Dict, List, Union, Optional
from loguru import logger
from app.rag.parsers.base import BaseParser


class PDFParser(BaseParser):
    """
    Decoupled PDF parser delegating text and structural extraction to the enterprise OCR subsystem.
    Handles both native text PDFs and scanned/image PDFs transparently without embedding OCR logic inside parser code.
    """
    def parse(
        self,
        file_input: Union[bytes, str],
        progress_callback: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        temp_path = None
        if isinstance(file_input, bytes):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
                tf.write(file_input)
                temp_path = tf.name
            target_path = temp_path
        else:
            target_path = file_input

        try:
            from app.services.ocr_service import extract_text_from_pdf
            logger.info(f"PDFParser: Delegating document extraction to OCR subsystem for '{os.path.basename(target_path)}'")
            extracted_text = extract_text_from_pdf(target_path, progress_callback=progress_callback)

            pages: List[Dict[str, Any]] = []
            page_blocks = re.split(r"--- \[Page (\d+)\] ---", extracted_text)

            if len(page_blocks) > 1:
                # Page markers present: re.split produces [before_first, page_1_num, page_1_text, page_2_num, page_2_text, ...]
                for i in range(1, len(page_blocks), 2):
                    page_num = int(page_blocks[i])
                    page_text = page_blocks[i + 1].strip() if (i + 1) < len(page_blocks) else ""
                    pages.append({
                        "text": page_text,
                        "page_number": page_num,
                        "section_title": None,
                        "tables": [],
                    })
            else:
                # Single continuous text block without markers
                pages.append({
                    "text": extracted_text.strip(),
                    "page_number": 1,
                    "section_title": None,
                    "tables": [],
                })

            logger.info(f"PDFParser: Document parsing complete. Produced {len(pages)} page structure objects.")
            return pages
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception as err:
                    logger.warning(f"PDFParser: Failed to clean up temp file '{temp_path}': {err}")
