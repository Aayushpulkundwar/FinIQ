import hashlib
import re
from typing import List, Dict, Any, Tuple, Optional
from uuid import UUID
from loguru import logger
from app.core.config import settings


def should_discard_chunk(text: str) -> Tuple[bool, str]:
    """
    Evaluates whether the chunk is low-value/noise (UI chrome, TOC, repeated keywords).
    """
    text_clean = text.strip()
    if not text_clean:
        return True, "Empty text"

    # 1. Unique word ratio
    words = [w.strip(".,;:!?()[]{}'\"").lower() for w in text_clean.split() if w.strip()]
    if words:
        unique_ratio = len(set(words)) / len(words)
        if len(words) >= 10 and unique_ratio < 0.25:
            return True, f"Low unique word ratio ({unique_ratio:.2f})"

    # 2. UI Chrome / Navigation lists (many lines, very few words per line)
    lines = [l.strip() for l in text_clean.split("\n") if l.strip()]
    if lines:
        word_counts = [len(l.split()) for l in lines]
        avg_words = sum(word_counts) / len(lines)
        if len(lines) >= 5 and avg_words < 1.5:
            return True, f"UI chrome / vertical navigation (avg words per line = {avg_words:.2f})"

    # 3. Table of contents / Page-index patterns (lines matching: <title> <page number>)
    if lines:
        toc_pattern = re.compile(r"^.{3,60}\s+\d{1,4}$")
        toc_lines = sum(1 for l in lines if toc_pattern.match(l))
        toc_ratio = toc_lines / len(lines)
        if len(lines) >= 3 and toc_ratio > 0.5:
            return True, f"TOC page index (TOC line ratio = {toc_ratio:.2f})"

    return False, ""


def extract_section_title_heuristic(text: str) -> Optional[str]:
    """
    Fallback method to extract section heading from chunk content.
    Looks at first few lines, looking for short title-case/all-caps line without ending punctuation.
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:4]:
        # Skip pure page numbers or lines containing "page"
        if line.isdigit() or re.match(r'^\d+$', line):
            continue
        if "page" in line.lower():
            continue
        if 3 <= len(line) <= 80:
            if not line[0].isalnum():
                continue
            if line[0].isalpha() and not line[0].isupper():
                continue
            if line[-1] in ('.', '?', '!', ',', ';', ':'):
                continue
            if ".." in line or "..." in line:
                continue
            return line
    return None


def classify_financial_statement(text: str) -> Optional[str]:
    """
    Heuristically classifies segment/statement type of the chunk text.
    """
    text_lower = text.lower()
    
    income_statement_sigs = [
        "income statement", "statement of profit and loss", "profit & loss", 
        "revenue from operations", "diluted eps", "earning per share", "profit before tax"
    ]
    balance_sheet_sigs = [
        "balance sheet", "statement of financial position", "equity and liabilities", 
        "share capital", "non-current assets", "current assets", "total equity"
    ]
    cash_flow_sigs = [
        "cash flow statement", "statement of cash flows", "operating activities", 
        "investing activities", "financing activities", "cash and cash equivalents"
    ]
    notes_sigs = [
        "notes to the financial statements", "notes forming part of", 
        "significant accounting policies", "notes to accounts", "note no."
    ]
    mda_sigs = [
        "management discussion", "md&a", "management's discussion and analysis", 
        "operational review", "industry overview"
    ]
    risks_sigs = [
        "risk factors", "key risks", "risk management", "principal risks"
    ]
    esg_sigs = [
        "esg", "sustainability", "environmental", "social and governance", 
        "corporate social responsibility", "esg report", "carbon footprint"
    ]
    chairman_sigs = [
        "chairman's message", "letter to shareholders", "from the chairman", 
        "chairman's letter"
    ]
    governance_sigs = [
        "corporate governance", "board of directors", "governance report", 
        "board committees", "directors' report"
    ]
    
    scores = {
        "income_statement": sum(1 for sig in income_statement_sigs if sig in text_lower),
        "balance_sheet": sum(1 for sig in balance_sheet_sigs if sig in text_lower),
        "cash_flow": sum(1 for sig in cash_flow_sigs if sig in text_lower),
        "notes": sum(1 for sig in notes_sigs if sig in text_lower),
        "mda": sum(1 for sig in mda_sigs if sig in text_lower),
        "risks": sum(1 for sig in risks_sigs if sig in text_lower),
        "esg": sum(1 for sig in esg_sigs if sig in text_lower),
        "chairman_message": sum(1 for sig in chairman_sigs if sig in text_lower),
        "governance": sum(1 for sig in governance_sigs if sig in text_lower),
    }
    
    best_class, max_score = max(scores.items(), key=lambda x: x[1])
    return best_class if max_score > 0 else None


def detect_business_segments(text: str) -> List[str]:
    text_lower = text.lower()
    possible_segments = ["textiles", "retail", "chemicals", "apparel", "brands"]
    return [seg for seg in possible_segments if seg in text_lower]


class DocumentChunker:
    """
    Segments parsed document page structures into configurable overlapping chunks.
    Injects source information and metadata parameters into every chunk dictionary.
    """
    @staticmethod
    def chunk_document(
        pages: List[Dict[str, Any]],
        document_id: UUID,
        company_id: UUID,
        document_type: str,
        fiscal_year: int,
        chunk_size: int = 2000,
        chunk_overlap: int = 400,
    ) -> List[Dict[str, Any]]:
        # 1. Header/Footer Repetition Detection
        line_counts = {}
        total_pages = len(pages)
        for page in pages:
            lines = [l.strip() for l in page.get("text", "").split("\n") if l.strip()]
            for line in set(lines):
                line_counts[line] = line_counts.get(line, 0) + 1
        
        # Identify repeating header/footers (present on >= 20% of pages, minimum 3 pages if total_pages >= 3)
        threshold = max(3, int(total_pages * 0.20)) if total_pages >= 3 else 2
        repeating_lines = {line for line, count in line_counts.items() if count >= threshold}

        chunks = []
        chunk_index = 0
        seen_chunk_hashes = set()

        # Collect blocks across all pages, merging fragmented paragraphs across boundaries
        all_blocks = []  # List of dict: {"text": str, "page_number": int, "section_title": str}
        
        for page in pages:
            raw_text = page.get("text", "")
            page_number = page.get("page_number", 1)
            page_section_title = page.get("section_title")
            
            if not raw_text.strip():
                continue
                
            # Strip repeating header/footer lines from the page text
            lines = [l for l in raw_text.split("\n")]
            cleaned_lines = []
            for l in lines:
                if l.strip() in repeating_lines:
                    continue
                cleaned_lines.append(l)
            text = "\n".join(cleaned_lines).strip()
            
            if not text:
                continue
                
            page_blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
            
            for block in page_blocks:
                # Check if we should merge with the last block of the previous page
                if all_blocks:
                    last_block = all_blocks[-1]
                    last_text = last_block["text"]
                    if (
                        last_text
                        and last_text[-1] not in ('.', '!', '?')
                        and last_text[-1].isalnum()
                        and not last_text.endswith("...")
                        and block
                        and block[0].islower()
                    ):
                        # Merge them!
                        last_block["text"] = last_text + " " + block
                        continue
                
                all_blocks.append({
                    "text": block,
                    "page_number": page_number,
                    "section_title": page_section_title
                })

        # 2. Semantic Split by Heading and Paragraph Boundaries
        page_chunks = []
        current_blocks = []
        current_len = 0
        current_page = 1
        current_section_title = None

        for item in all_blocks:
            block = item["text"]
            page_number = item["page_number"]
            page_section_title = item["section_title"]
            block_len = len(block)

            if block_len > chunk_size:
                # Flush pending blocks
                if current_blocks:
                    page_chunks.append({
                        "text": "\n\n".join(current_blocks),
                        "page_number": current_page,
                        "section_title": current_section_title
                    })
                    current_blocks = []
                    current_len = 0
                
                # Split oversized block by line to preserve row chunks or small blocks
                lines = [l.strip() for l in block.split("\n") if l.strip()]
                sub_lines = []
                sub_len = 0
                for line in lines:
                    if sub_len + len(line) + 1 > chunk_size:
                        if sub_lines:
                            page_chunks.append({
                                "text": "\n".join(sub_lines),
                                "page_number": page_number,
                                "section_title": page_section_title
                            })
                        sub_lines = [line]
                        sub_len = len(line)
                    else:
                        sub_lines.append(line)
                        sub_len += len(line) + 1
                if sub_lines:
                    page_chunks.append({
                        "text": "\n".join(sub_lines),
                        "page_number": page_number,
                        "section_title": page_section_title
                    })
                continue

            if current_len + block_len + 2 > chunk_size:
                page_chunks.append({
                    "text": "\n\n".join(current_blocks),
                    "page_number": current_page,
                    "section_title": current_section_title
                })
                
                # Build overlap blocks from previous chunk
                overlap_blocks = []
                overlap_len = 0
                for prev in reversed(current_blocks):
                    if overlap_len + len(prev) + 2 <= chunk_overlap:
                        overlap_blocks.insert(0, prev)
                        overlap_len += len(prev) + 2
                    else:
                        break
                current_blocks = overlap_blocks + [block]
                current_len = sum(len(b) for b in current_blocks) + (len(current_blocks) - 1) * 2
                current_page = page_number
                current_section_title = page_section_title
            else:
                if not current_blocks:
                    current_page = page_number
                    current_section_title = page_section_title
                current_blocks.append(block)
                current_len += block_len + (2 if current_len > 0 else 0)

        if current_blocks:
            page_chunks.append({
                "text": "\n\n".join(current_blocks),
                "page_number": current_page,
                "section_title": current_section_title
            })

        # 3. Filter, Classify, and Process each chunk
        for item in page_chunks:
            chunk_text = item["text"].strip()
            page_number = item["page_number"]
            page_section_title = item["section_title"]

            if not chunk_text:
                continue

            # Hash similarity check (Deduplication)
            norm_text = re.sub(r"\s+", "", chunk_text.lower())
            chunk_hash = hashlib.md5(norm_text.encode("utf-8")).hexdigest()
            if chunk_hash in seen_chunk_hashes:
                logger.warning(
                    f"DISCARDED DUPLICATE CHUNK: doc_id={document_id}, page={page_number}, "
                    f"chunk_index={chunk_index}. Preview: {chunk_text[:100]!r}"
                )
                continue

            # Pre-embedding filtering steps
            discard, reason = should_discard_chunk(chunk_text)
            if discard:
                logger.warning(
                    f"DISCARDED JUNK CHUNK: doc_id={document_id}, page={page_number}, "
                    f"chunk_index={chunk_index}, Reason='{reason}'. Preview: {chunk_text[:100]!r}"
                )
                continue

            # Determine section title (with heuristic fallback)
            section_title = page_section_title or extract_section_title_heuristic(chunk_text)

            # Financial Document Intelligence classification
            statement_type = classify_financial_statement(chunk_text)
            business_segments = detect_business_segments(chunk_text)

            # Map statement_type to user-specified section_type
            section_type = None
            if statement_type in ("income_statement", "balance_sheet", "cash_flow"):
                section_type = "financial_statements"
            elif statement_type == "mda":
                section_type = "md&a"
            elif statement_type in ("governance", "chairman_message"):
                section_type = "governance"
            elif statement_type == "risks":
                section_type = "risk_factors"
            elif statement_type == "notes":
                section_type = "notes_to_accounts"
            elif statement_type is not None:
                section_type = statement_type

            seen_chunk_hashes.add(chunk_hash)

            chunks.append({
                "document_id": document_id,
                "chunk_text": chunk_text,
                "metadata": {
                    "document_id": str(document_id),
                    "company_id": str(company_id),
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                    "document_type": document_type,
                    "fiscal_year": fiscal_year,
                    "section_title": section_title,
                    "statement_type": statement_type,
                    "section_type": section_type,
                    "business_segments": business_segments,
                    "file_hash": chunk_hash
                }
            })
            chunk_index += 1

        return chunks
