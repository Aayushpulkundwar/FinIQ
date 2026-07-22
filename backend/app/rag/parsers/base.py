from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseParser(ABC):
    """
    Abstract Base Parser defining the interface for file text extraction.
    """
    @abstractmethod
    def parse(self, file_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Parses document bytes, returning page segments mapping text content to pages.
        Returns:
            List[Dict[str, Any]]: List of pages, where each page is:
                {"text": "page content text", "page_number": 1-based page index}
        """
        pass
