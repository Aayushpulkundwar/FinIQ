import io
from pptx import Presentation
from typing import List, Dict, Any
from app.rag.parsers.base import BaseParser


class PptxParser(BaseParser):
    """
    Parser for extracting text from Microsoft PowerPoint (.pptx) slide decks.
    Each slide is treated as a physical page.
    """
    def parse(self, file_bytes: bytes) -> List[Dict[str, Any]]:
        prs = Presentation(io.BytesIO(file_bytes))
        pages = []

        for slide_idx, slide in enumerate(prs.slides):
            slide_text_parts = []
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    slide_text_parts.append(shape.text.strip())

            pages.append({
                "text": "\n".join(slide_text_parts),
                "page_number": slide_idx + 1
            })

        return pages
