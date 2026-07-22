import re
from typing import Dict, List, Any, Optional, Tuple
from loguru import logger
from app.schemas.retrieval import RetrievalResponse
from pydantic import BaseModel, Field
from app.core.config import settings

# Maps financial field names to their regex search patterns (retained for fallback)
FIELD_PATTERNS: Dict[str, List[str]] = {
    "revenue": [
        r"(?:total\s+)?revenue[:\s]+[\$₹€£]?\s*([\d,\.]+\s*(?:billion|million|crore|lakh|bn|mn|cr)?)",
        r"net\s+sales[:\s]+[\$₹€£]?\s*([\d,\.]+\s*(?:billion|million|crore|bn|mn|cr)?)",
        r"turnover[:\s]+[\$₹€£]?\s*([\d,\.]+\s*(?:billion|million|crore|bn|mn|cr)?)",
    ],
    "ebitda": [
        r"ebitda[:\s]+[\$₹€£]?\s*([\d,\.]+\s*(?:billion|million|crore|bn|mn|cr)?)",
        r"earnings\s+before\s+interest[,\s]+taxes[,\s]+depreciation[:\s]+[\$₹€£]?\s*([\d,\.]+)",
    ],
    "operating_income": [
        r"operating\s+(?:income|profit)[:\s]+[\$₹€£]?\s*([\d,\.]+\s*(?:billion|million|crore|bn|mn|cr)?)",
        r"ebit[:\s]+[\$₹€£]?\s*([\d,\.]+\s*(?:billion|million|crore|bn|mn|cr)?)",
    ],
    "net_profit": [
        r"net\s+(?:profit|income|earnings)[:\s]+[\$₹€£]?\s*([\d,\.]+\s*(?:billion|million|crore|bn|mn|cr)?)",
        r"profit\s+after\s+tax[:\s]+[\$₹€£]?\s*([\d,\.]+)",
    ],
    "eps": [
        r"(?:basic\s+)?(?:diluted\s+)?(?:earnings|eps)\s+per\s+share[:\s]+[\$₹€£]?\s*([\d,\.]+)",
        r"eps[:\s]+[\$₹€£]?\s*([\d,\.]+)",
    ],
    "total_assets": [
        r"total\s+assets[:\s]+[\$₹€£]?\s*([\d,\.]+\s*(?:billion|million|crore|bn|mn|cr)?)",
    ],
    "total_liabilities": [
        r"total\s+liabilities[:\s]+[\$₹€£]?\s*([\d,\.]+\s*(?:billion|million|crore|bn|mn|cr)?)",
    ],
    "shareholders_equity": [
        r"(?:total\s+)?(?:shareholders?|stockholders?)\s+equity[:\s]+[\$₹€£]?\s*([\d,\.]+\s*(?:billion|million|crore|bn|mn|cr)?)",
    ],
    "operating_cash_flow": [
        r"(?:net\s+)?cash\s+(?:from|provided\s+by)\s+operating[:\s]+[\$₹€£]?\s*([\d,\.]+\s*(?:billion|million|crore|bn|mn|cr)?)",
        r"operating\s+cash\s+flow[:\s]+[\$₹€£]?\s*([\d,\.]+)",
    ],
    "free_cash_flow": [
        r"free\s+cash\s+flow[:\s]+[\$₹€£]?\s*([\d,\.]+\s*(?:billion|million|crore|bn|mn|cr)?)",
    ],
    "capex": [
        r"(?:capital\s+expenditure|capex)[:\s]+[\$₹€£]?\s*([\d,\.]+\s*(?:billion|million|crore|bn|mn|cr)?)",
        r"purchase\s+of\s+(?:property|ppe)[:\s]+[\$₹€£]?\s*([\d,\.]+)",
    ],
}


# ---------------------------------------------------------------------------
# LLM Extraction Schemas
# ---------------------------------------------------------------------------

class FieldExtraction(BaseModel):
    """Extraction details for a single financial line item."""
    value: Optional[float] = Field(
        None, 
        description="The numeric value in absolute units (e.g. if document says '8,394 Crores' and currency is INR, value must be 83940000000; if document says '145.2 Million' and currency is USD, value must be 145200000). Set to null/None if not found."
    )
    supporting_text_excerpt: Optional[str] = Field(
        None, 
        description="A direct verbatim text snippet from the provided context that contains or supports this value. Set to null/None if not found."
    )


class FinancialExtractionSchema(BaseModel):
    """Full financial statement extraction response from LLM."""
    revenue: Optional[FieldExtraction] = Field(None, description="Total revenue, net sales, or turnover.")
    ebitda: Optional[FieldExtraction] = Field(None, description="EBITDA (Earnings Before Interest, Taxes, Depreciation, and Amortization).")
    operating_income: Optional[FieldExtraction] = Field(None, description="Operating income, operating profit, or EBIT.")
    net_profit: Optional[FieldExtraction] = Field(None, description="Net profit, net income, or Profit After Tax (PAT).")
    eps: Optional[FieldExtraction] = Field(None, description="Earnings Per Share (basic or diluted).")
    total_assets: Optional[FieldExtraction] = Field(None, description="Total assets.")
    total_liabilities: Optional[FieldExtraction] = Field(None, description="Total liabilities.")
    shareholders_equity: Optional[FieldExtraction] = Field(None, description="Shareholders' equity or common stock equity.")
    operating_cash_flow: Optional[FieldExtraction] = Field(None, description="Cash flow from operating activities.")
    free_cash_flow: Optional[FieldExtraction] = Field(None, description="Free cash flow.")
    capex: Optional[FieldExtraction] = Field(None, description="Capital expenditures (CAPEX).")


# ---------------------------------------------------------------------------
# Main Parser Class
# ---------------------------------------------------------------------------

class FinancialParser:
    """
    Parses structured financial values from retrieved document chunks.
    Uses LLM structured outputs as primary, falls back to regex matching.
    """

    @classmethod
    def parse_chunks(
        cls,
        chunks_by_group: Dict[str, List[RetrievalResponse]]
    ) -> Dict[str, Tuple[Optional[float], Optional[RetrievalResponse]]]:
        """
        Extracts financial fields from retrieved chunks.
        First tries Gemini LLM structured output. On failure/empty, falls back to regex.
        """
        # Collect all unique chunks
        all_chunks: List[RetrievalResponse] = []
        for chunks in chunks_by_group.values():
            all_chunks.extend(chunks)

        seen_texts = set()
        unique_chunks: List[RetrievalResponse] = []
        for chunk in all_chunks:
            if chunk.chunk_text not in seen_texts:
                seen_texts.add(chunk.chunk_text)
                unique_chunks.append(chunk)

        # Sort by similarity score descending
        unique_chunks.sort(key=lambda c: c.similarity_score, reverse=True)

        if not unique_chunks:
            logger.warning("No chunks available for parsing.")
            return {field: (None, None) for field in FIELD_PATTERNS}

        # 1. OpenRouter extraction
        openrouter_key = settings.OPENROUTER_API_KEY
        if openrouter_key and "placeholder" not in (openrouter_key or "").lower():
            try:
                logger.info("FinancialParser: Attempting OpenRouter-based financial parsing.")
                extracted = cls._parse_with_openrouter(unique_chunks)
                if extracted:
                    logger.info("FinancialParser: OpenRouter financial parsing succeeded.")
                    return extracted
            except Exception as e:
                logger.warning(f"FinancialParser: OpenRouter parsing failed: {e}.")

        # 2. Regex Fallback
        logger.info("FinancialParser: Falling back to regex-based financial parsing.")
        return cls._parse_with_regex(unique_chunks)

    @classmethod
    def _parse_with_openrouter(
        cls,
        unique_chunks: List[RetrievalResponse],
    ) -> Optional[Dict[str, Tuple[Optional[float], Optional[RetrievalResponse]]]]:
        """
        Uses OpenRouter (sync) to extract financial fields from chunks.
        """
        from app.core.openrouter_client import openrouter_chat_sync
        from app.core.config import settings as _settings
        import json
        import re as _re

        # Build contextual block
        context_blocks = []
        for idx, chunk in enumerate(unique_chunks):
            context_blocks.append(
                f"--- Chunk Index {idx} (Doc: {chunk.document_title}, Page: {chunk.page_number}, Sec: {chunk.section_title}) ---\n"
                f"{chunk.chunk_text}"
            )
        context_text = "\n\n".join(context_blocks)

        ref_chunk = unique_chunks[0]
        year = ref_chunk.fiscal_year
        doc_type = ref_chunk.document_type.value

        system_msg = (
            "You are a professional financial analyst. Extract financial metrics from the document context "
            "and return ONLY a valid JSON object with these exact keys: "
            "revenue, ebitda, operating_income, net_profit, eps, total_assets, total_liabilities, "
            "shareholders_equity, operating_cash_flow, free_cash_flow, capex. "
            "Each key must map to an object with 'value' (numeric, absolute units, null if not found) "
            "and 'supporting_text_excerpt' (short verbatim snippet, null if not found). "
            "Do NOT include markdown fences, prose, or extra keys."
        )
        user_msg = (
            f"Fiscal year: {year}. Document: {ref_chunk.document_title} ({doc_type}).\n\n"
            f"CRITICAL: Normalize all values to absolute base units "
            f"(e.g. '8,394 Crores INR' -> 83940000000; '145.2 Million USD' -> 145200000).\n\n"
            f"Context:\n{context_text}"
        )

        logger.info(f"FinancialParser: Invoking LLM (model={_settings.OPENROUTER_MODEL}) for year {year}.")
        try:
            llm_result = openrouter_chat_sync(
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                model=_settings.OPENROUTER_MODEL,
                api_key=_settings.OPENROUTER_API_KEY or "",
                base_url=_settings.OPENROUTER_BASE_URL,
                caller_label="FinancialParser._parse_with_openrouter",
            )
        except Exception as llm_exc:
            # Both OpenRouter and Ollama fallback failed — let caller use regex.
            logger.warning(
                f"FinancialParser: LLM call failed entirely ({llm_exc}). "
                "Falling back to regex extractor."
            )
            return None

        logger.info(
            f"FinancialParser: LLM extraction served by provider={llm_result.provider_used}."
        )
        raw_text = llm_result.content

        # ---------------------------------------------------------------
        # Strict JSON schema validation BEFORE trusting any LLM output.
        # This guard applies equally to OpenRouter and Ollama responses.
        # If the output fails, return None → regex fallback takes over.
        # ---------------------------------------------------------------
        required_fields = set(FIELD_PATTERNS.keys())
        raw_clean = raw_text.strip()
        if raw_clean.startswith("```"):
            raw_clean = _re.sub(r"^```(?:json)?\s*|```$", "", raw_clean, flags=_re.MULTILINE).strip()
        try:
            data = json.loads(raw_clean)
        except json.JSONDecodeError as json_exc:
            logger.warning(
                f"FinancialParser: LLM output from provider={llm_result.provider_used} "
                f"is not valid JSON ({json_exc}). Falling back to regex."
            )
            return None

        if not isinstance(data, dict):
            logger.warning(
                f"FinancialParser: LLM output from provider={llm_result.provider_used} "
                "is not a JSON object. Falling back to regex."
            )
            return None

        # Check that all required keys are present
        missing_keys = required_fields - set(data.keys())
        if missing_keys:
            logger.warning(
                f"FinancialParser: LLM output from provider={llm_result.provider_used} "
                f"is missing required keys: {missing_keys}. Falling back to regex."
            )
            return None

        # Check each value has the expected shape {"value": ..., "supporting_text_excerpt": ...}
        for field_name, field_data in data.items():
            if field_name not in required_fields:
                continue  # extra keys are tolerated
            if not isinstance(field_data, dict) or "value" not in field_data:
                logger.warning(
                    f"FinancialParser: LLM output from provider={llm_result.provider_used} "
                    f"has malformed field '{field_name}': {field_data!r}. Falling back to regex."
                )
                return None

        # Validation passed — proceed with extraction
        mapped_results: Dict[str, Tuple[Optional[float], Optional[RetrievalResponse]]] = {}
        for field in FIELD_PATTERNS.keys():
            field_data = data.get(field)
            if not field_data or field_data.get("value") is None:
                mapped_results[field] = (None, None)
                continue

            value = field_data.get("value")
            try:
                value = float(value)
            except (TypeError, ValueError):
                mapped_results[field] = (None, None)
                continue

            # Locate contributing chunk via supporting snippet
            best_chunk = None
            excerpt = (field_data.get("supporting_text_excerpt") or "").lower().strip()
            if excerpt:
                for chunk in unique_chunks:
                    if excerpt in chunk.chunk_text.lower():
                        best_chunk = chunk
                        break
                if not best_chunk:
                    excerpt_words = set(excerpt.split())
                    best_chunk = max(
                        unique_chunks,
                        key=lambda c: len(excerpt_words & set(c.chunk_text.lower().split())),
                        default=None,
                    )
            if not best_chunk and unique_chunks:
                best_chunk = unique_chunks[0]

            logger.info(
                f"FinancialParser: provider={llm_result.provider_used} extracted "
                f"'{field}': {value} (page {best_chunk.page_number if best_chunk else 'unknown'})"
            )
            mapped_results[field] = (value, best_chunk)

        # Return None if nothing was extracted (triggers regex fallback)
        if all(v[0] is None for v in mapped_results.values()):
            return None
        return mapped_results

    @classmethod
    def _parse_with_regex(
        cls,
        unique_chunks: List[RetrievalResponse]
    ) -> Dict[str, Tuple[Optional[float], Optional[RetrievalResponse]]]:
        """Legacy regex parsing logic (used as fallback)."""
        parsed: Dict[str, Tuple[Optional[float], Optional[RetrievalResponse]]] = {
            field: (None, None) for field in FIELD_PATTERNS
        }

        for chunk in unique_chunks:
            text = chunk.chunk_text.lower()
            for field, patterns in FIELD_PATTERNS.items():
                if parsed[field][0] is not None:
                    continue  # already found
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        raw_value = match.group(1).strip()
                        # Convert to float since standard interface now uses numeric
                        from app.services.financial_intelligence.normalizer import FinancialNormalizer
                        numeric_val = FinancialNormalizer.normalize(raw_value)
                        if numeric_val is not None:
                            parsed[field] = (numeric_val, chunk)
                            logger.debug(f"Regex Parsed '{field}': '{numeric_val}' from chunk page {chunk.page_number}")
                            break

        return parsed
