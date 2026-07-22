import fitz  # PyMuPDF
from typing import List, Dict, Any
from app.rag.parsers.base import BaseParser


class PDFParser(BaseParser):
    """
    Parser for extracting text from PDF documents page by page.
    """
    def parse(self, file_bytes: bytes) -> List[Dict[str, Any]]:
        pages = []
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        try:
            # Extract outline bookmarks (TOC)
            toc = doc.get_toc()
            page_sections = {}
            if toc:
                # Sort bookmarks by page number (1-indexed)
                sorted_toc = []
                for entry in toc:
                    if len(entry) >= 3 and isinstance(entry[2], int):
                        sorted_toc.append(entry)
                sorted_toc.sort(key=lambda x: x[2])

                # Map each page to its section title
                for page_idx in range(len(doc)):
                    page_num = page_idx + 1
                    current_section = None
                    for lvl, title, p_num in sorted_toc:
                        if p_num <= page_num:
                            current_section = title
                        else:
                            break
                    if current_section:
                        # Clean if it is just a filename
                        title_clean = current_section.strip()
                        if title_clean.lower().endswith(".pdf") or ".pdf" in title_clean.lower():
                            current_section = None
                        else:
                            current_section = title_clean
                    if current_section:
                        page_sections[page_num] = current_section

            def is_inside_bbox(block_bbox, table_bboxes):
                bx0, by0, bx1, by1 = block_bbox
                for tx0, ty0, tx1, ty1 in table_bboxes:
                    overlap_x = max(0, min(bx1, tx1) - max(bx0, tx0))
                    overlap_y = max(0, min(by1, ty1) - max(by0, ty0))
                    overlap_area = overlap_x * overlap_y
                    block_area = (bx1 - bx0) * (by1 - by0)
                    if block_area > 0 and (overlap_area / block_area) > 0.5:
                        return True
                return False

            for page_idx, page in enumerate(doc):
                page_tables = []
                table_bboxes = []
                
                # Extract tables first and save bounding boxes
                try:
                    tables = page.find_tables()
                    for table in tables:
                        table_data = table.extract()
                        if table_data and len(table_data) > 0:
                            # Filter empty rows
                            valid_rows = []
                            for r in table_data:
                                if r and any(cell is not None and str(cell).strip() for cell in r):
                                    valid_rows.append(r)
                            
                            if valid_rows:
                                num_cols = len(valid_rows[0])
                                markdown = []
                                # Header
                                headers = [str(cell or "").strip().replace("\n", " ") for cell in valid_rows[0]]
                                markdown.append("| " + " | ".join(headers) + " |")
                                # Separator
                                markdown.append("| " + " | ".join(["---"] * num_cols) + " |")
                                # Data rows
                                for row in valid_rows[1:]:
                                    cells = []
                                    for i in range(num_cols):
                                        val = row[i] if i < len(row) else ""
                                        cells.append(str(val or "").strip().replace("\n", " "))
                                    markdown.append("| " + " | ".join(cells) + " |")
                                
                                md_table = "\n".join(markdown)
                                if md_table.strip():
                                    page_tables.append(md_table)
                                    table_bboxes.append(table.bbox)
                except Exception as table_err:
                    from loguru import logger
                    logger.warning(f"Failed to find or extract tables on page {page_idx+1}: {table_err}")

                # Extract text blocks and exclude those inside table bounding boxes
                blocks = page.get_text("blocks")
                text_parts = []
                if isinstance(blocks, list):
                    for b in blocks:
                        if isinstance(b, (tuple, list)) and len(b) >= 5:
                            block_bbox = b[:4]
                            block_text = str(b[4]).strip()
                            if block_text and not is_inside_bbox(block_bbox, table_bboxes):
                                text_parts.append(block_text)
                        else:
                            b_str = str(b).strip()
                            if b_str:
                                text_parts.append(b_str)
                else:
                    # If blocks is just a string or None, fallback to plain text conversion
                    if isinstance(blocks, str) and blocks.strip():
                        text_parts.append(blocks.strip())
                    elif not blocks:
                        # Attempt regular text fallback
                        fallback_txt = page.get_text()
                        if fallback_txt and isinstance(fallback_txt, str) and fallback_txt.strip():
                            text_parts.append(fallback_txt.strip())
                
                text = "\n\n".join(text_parts)

                pages.append({
                    "text": text,
                    "page_number": page_idx + 1,  # 1-based index
                    "section_title": page_sections.get(page_idx + 1),
                    "tables": page_tables
                })
        finally:
            doc.close()
        return pages
