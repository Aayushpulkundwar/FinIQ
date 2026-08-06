from abc import ABC, abstractmethod


class BaseOCRProvider(ABC):
    """
    Abstract base class for pluggable OCR providers (e.g., Nemotron Parse v1.2, EasyOCR, Tesseract).
    Ensures modularity, dependency injection, and clean provider switching.
    """
    @abstractmethod
    def process_page_image(self, image_bytes: bytes, page_num: int) -> str:
        """
        Processes a rendered high-resolution page image bytes and returns extracted text.
        Must preserve document structure, headings, paragraphs, lists, and markdown tables where available.
        """
        pass
