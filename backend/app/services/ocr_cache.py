import hashlib
import os
from typing import Optional
from loguru import logger
from app.core.config import settings


class OCRCache:
    """
    Persistent file-based cache for OCR processing results.
    Generates SHA256 hashes of PDF files and caches extracted text under `.cache/ocr/{sha256}.txt`.
    Prevents duplicate OCR processing of identical files across runs.
    """
    def __init__(self, cache_dir: Optional[str] = None, enabled: Optional[bool] = None):
        self.cache_dir = cache_dir or settings.OCR_CACHE_DIR
        self.enabled = enabled if enabled is not None else settings.OCR_CACHE_ENABLED
        if self.enabled:
            os.makedirs(self.cache_dir, exist_ok=True)

    @staticmethod
    def compute_sha256(pdf_path: str) -> str:
        """Computes SHA256 checksum of a file in 64KB chunks."""
        hasher = hashlib.sha256()
        with open(pdf_path, "rb") as f:
            while chunk := f.read(64 * 1024):
                hasher.update(chunk)
        return hasher.hexdigest()

    def get(self, pdf_path: str) -> Optional[str]:
        """
        Retrieves cached OCR text for the given PDF file if present.
        Returns extracted text string if cache hit, None if cache miss or cache disabled.
        """
        if not self.enabled:
            return None

        try:
            doc_hash = self.compute_sha256(pdf_path)
            cache_file = os.path.join(self.cache_dir, f"{doc_hash}.txt")
            if os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    content = f.read()
                logger.info(f"OCRCache: HIT for '{os.path.basename(pdf_path)}' (hash={doc_hash[:12]}..., bytes={len(content)})")
                return content
            logger.info(f"OCRCache: MISS for '{os.path.basename(pdf_path)}' (hash={doc_hash[:12]}...)")
        except Exception as e:
            logger.warning(f"OCRCache: Failed to read cache for '{pdf_path}': {e}")
        return None

    def set(self, pdf_path: str, text: str) -> None:
        """Saves OCR text result to persistent disk cache."""
        if not self.enabled or not text:
            return

        try:
            doc_hash = self.compute_sha256(pdf_path)
            cache_file = os.path.join(self.cache_dir, f"{doc_hash}.txt")
            tmp_file = f"{cache_file}.tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp_file, cache_file)
            logger.info(f"OCRCache: Saved OCR result for '{os.path.basename(pdf_path)}' (hash={doc_hash[:12]}...)")
        except Exception as e:
            logger.warning(f"OCRCache: Failed to write cache for '{pdf_path}': {e}")
