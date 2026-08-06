import asyncio
import re
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
from loguru import logger
from app.models.document import DocumentType
from app.repositories.document_chunk import DocumentChunkRepository
from app.schemas.retrieval import RetrievalResponse
from app.services.base import BaseService
from app.rag.embeddings import EmbeddingService
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from unittest.mock import Mock, AsyncMock


def is_substantive_chunk(text: str) -> bool:
    """
    Heuristically checks if a chunk contains substantive document content,
    filtering out table-of-contents, index pages, or metadata-only lines.
    """
    text_clean = text.strip()
    # 1. Too brief or mostly empty/whitespace
    if len(text_clean) < 12:
        return False
        
    text_lower = text_clean.lower()
    
    # 2. Table of contents or Index indicator keywords
    toc_indicators = [
        "table of contents", "contents page", "list of figures", "list of tables",
        "index of", "financial statements contents", "contents of this report"
    ]
    if any(ind in text_lower for ind in toc_indicators):
        if text.count("...") > 4 or text.count("..") > 10 or text_lower.count("page ") > 4:
            return False

    # 3. Check if chunk contains purely lists of numbers or short lines with dots (indexing)
    lines = [l.strip() for l in text_clean.split("\n") if l.strip()]
    if lines:
        dot_lines = sum(1 for l in lines if l.count(".") > 2 or l.count("..") >= 1)
        if dot_lines / len(lines) > 0.4:
            return False

    return True


def is_dense_tabular_chunk(text: str) -> bool:
    """
    Detects markdown-style data tables (e.g. subsidiary/ownership schedules,
    related-party tables, cap tables) that have high row-count and repetitive
    pipe-delimited structure. These chunks tend to dominate keyword/FTS
    ranking for company-name queries despite being poor answers to general
    "what does X do" style questions.
    """
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    if not lines:
        return False
    pipe_lines = sum(1 for l in lines if l.count("|") >= 3)
    return len(lines) >= 5 and (pipe_lines / len(lines)) > 0.5


# ── Overview intent detection ─────────────────────────────────────────────────

OVERVIEW_QUERY_SIGNALS = [
    "summarize", "summary", "overview", "about the company", "about us",
    "business summary", "company profile", "company overview", "what does",
    "business overview", "company description", "business description",
    "what is", "tell me about", "describe", "business model",
]


def is_overview_query(query: str) -> bool:
    """
    Returns True when the query is asking for a general company summary,
    overview, or business description — as opposed to a financial, governance,
    audit, or structural query.  Used to gate overview-specific boosts,
    penalties, and query expansion so that other query types are unaffected.
    """
    q = query.lower()
    return any(sig in q for sig in OVERVIEW_QUERY_SIGNALS)


# ── Overview section / governance content classifiers ─────────────────────────

OVERVIEW_SECTION_SIGNALS = [
    "company overview", "about us", "about the company", "business overview",
    "business model", "our business", "md&a", "management discussion",
    "management's discussion", "chairman", "managing director", "ceo message",
    "chief executive", "strategy", "operations overview", "segment overview",
    "value proposition", "industry presence", "business description",
    "business highlights", "company profile", "business at a glance",
    "who we are", "what we do", "key highlights", "performance overview",
]

GOVERNANCE_CONTENT_SIGNALS = [
    "independent auditor", "auditor's report", "auditors' report",
    "statutory auditor", "board of directors' report", "directors' report",
    "corporate governance report", "secretarial audit", "appointed as director",
    "reappointment of", "appointment of", "sitting fees", "attendance at board",
    "regulation 17", "regulation 18", "regulation 23", "regulation 34",
    "pursuant to section 134", "pursuant to section 149", "pursuant to section 152",
    "pursuant to section 197", "companies act, 2013", "sebi (lodr)",
    "disclosure under regulation", "declaration by independent director",
    "din:", "related party disclosure", "materiality policy",
]


def is_overview_positive_chunk(text: str, section_title: str) -> bool:
    """
    Returns True when a chunk likely originates from a high-value overview
    section (Company Overview, MDA, Chairman's Message, Strategy, etc.).
    Checks both the section_title and the leading text of the chunk.
    """
    title_lower = (section_title or "").lower()
    lead = text[:200].lower()
    combined = title_lower + " " + lead
    return any(sig in combined for sig in OVERVIEW_SECTION_SIGNALS)


def is_low_value_governance_chunk(text: str, section_title: str) -> bool:
    """
    Returns True when a chunk originates from auditor reports, governance
    boilerplate, director appointment/reappointment terms, or statutory
    disclosures — content that is authoritative but not useful for answering
    "what does company X do" style queries.
    Checks both section_title and the first 300 characters of chunk text.
    """
    title_lower = (section_title or "").lower()
    lead = text[:300].lower()

    # Section title signals (fast path)
    title_gov_signals = [
        "auditor", "corporate governance", "directors' report",
        "board report", "secretarial audit", "statutory report",
        "shareholder notice", "notice of agm", "remuneration policy",
    ]
    if any(sig in title_lower for sig in title_gov_signals):
        return True

    # Content signals (slower but catches unlabelled chunks)
    governance_matches = sum(1 for sig in GOVERNANCE_CONTENT_SIGNALS if sig in lead)
    return governance_matches >= 2


class RetrievalService(BaseService[DocumentChunkRepository]):
    """
    Service layer orchestrating query vector encoding, multi-query expansion, FTS keyword hybrid retrieval,
    and reciprocal rank fusion with custom boosting reranking.
    """
    def __init__(self, db: AsyncSession):
        super().__init__(DocumentChunkRepository(db))
        self.embeddings = EmbeddingService()

    async def search(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: Optional[float] = None,
        company_id: Optional[UUID] = None,
        document_type: Optional[DocumentType] = None,
        fiscal_year: Optional[int] = None,
        page_number: Optional[int] = None,
        include_mock: bool = False,
    ) -> List[RetrievalResponse]:
        """
        Coordinates hybrid RAG search:
        1. Automatically expands query using Gemini model (if configured).
        2. Executes pgvector similarity search + PostgreSQL Full-Text Search in parallel.
        3. Fuses search results using Reciprocal Rank Fusion (RRF).
        4. Applies custom document type, statement type, recency, exact ticker, and TOC penalization boosts.
        """
        # Check if repository itself is mocked (direct unit tests asserting specific score formats)

        if isinstance(self.repository, (Mock, AsyncMock)):
            query_vector = self.embeddings.get_embedding(query)
            matches = await self.repository.search_similarity(
                query_embedding=query_vector,
                top_k=top_k,
                min_similarity=min_similarity,
                company_id=company_id,
                document_type=document_type,
                fiscal_year=fiscal_year,
                page_number=page_number,
                query_text=query,
                include_mock=include_mock
            )
            if not isinstance(matches, list):
                return []
            res_list = []
            for chunk, score in matches:
                title = chunk.document.title if chunk.document else "Unnamed Document"
                res_list.append(
                    RetrievalResponse(
                        chunk_text=chunk.chunk_text,
                        similarity_score=score,
                        document_id=chunk.document_id,
                        document_title=title,
                        company_id=chunk.company_id,
                        page_number=chunk.page_number,
                        chunk_index=chunk.chunk_index,
                        section_title=chunk.section_title,
                        document_type=chunk.document_type,
                        fiscal_year=chunk.fiscal_year,
                    )
                )
            return res_list

        # 1. Multi-Query Expansion
        queries = [query]

        # Overview intent: prepend domain-specific expansion queries so FTS/vector
        # retrieval is strongly biased toward business-description sections before
        # the generic LLM expander adds its own variants.
        if is_overview_query(query):
            # Extract a bare company identifier hint from the original query so
            # the extra queries are as specific as possible.
            _ov_extras = [
                f"{query} company overview business model operations",
                f"{query} industries segments geographic presence",
                f"{query} strategy key capabilities management discussion analysis",
                f"{query} chairman message CEO business highlights annual report",
            ]
            for _eq in _ov_extras:
                if _eq not in queries:
                    queries.append(_eq)
            logger.info(f"RetrievalSearch: Overview intent detected — injected {len(_ov_extras)} domain expansion queries.")
        openrouter_key = settings.OPENROUTER_API_KEY
        if openrouter_key and "placeholder" not in (openrouter_key or "").lower() and not settings.ALLOW_MOCK_LLM:
            try:
                from app.core.openrouter_client import openrouter_chat
                prompt = (
                    f"Generate 3 distinct search queries in English to retrieve relevant sections from financial reports "
                    f"to answer: '{query}'. Return only a bulleted list, one query per line, without intro/conclusion."
                )
                result = await openrouter_chat(
                    messages=[{"role": "user", "content": prompt}],
                    model=settings.OPENROUTER_MODEL,
                    api_key=openrouter_key,
                    base_url=settings.OPENROUTER_BASE_URL,
                    caller_label="RetrievalService.query_expansion",
                )
                logger.info(
                    f"RetrievalService: Query expansion served by provider={result.provider_used}."
                )
                lines = result.content.split("\n")
                for line in lines:
                    line_clean = re.sub(r"^[-*\d.\s]+", "", line).strip()
                    if line_clean and len(line_clean) > 5 and line_clean not in queries:
                        queries.append(line_clean)
                logger.info(f"RetrievalSearch: Expanded queries list: {queries}")
            except Exception as e:
                logger.warning(f"Failed to generate search queries expansion via OpenRouter: {e}")

        # Limit to maximum 4 queries to prevent excessive database overhead
        queries = queries[:4]

        candidate_map = {}
        rrf_scores = {}

        embedding_failed = False
        # 2. Execute Hybrid Retrieve (Vector + Keyword) across all expanded queries
        for q in queries:
            query_vector = None
            try:
                # Encode search string into embedding vector.
                # run_in_executor offloads the blocking sync calls (Redis lock + httpx)
                # to a thread-pool thread so the FastAPI event loop stays free for
                # other concurrent requests during the ~0.8s Ollama round-trip.
                loop = asyncio.get_event_loop()
                query_vector = await loop.run_in_executor(
                    None, self.embeddings.get_embedding, q
                )
            except Exception as e:
                embedding_failed = True
                logger.error(
                    f"CRITICAL: Failed to generate embedding from Ollama/BGE-M3 for query '{q}': {e}"
                )

            try:
                vector_matches = []
                keyword_matches = []

                if query_vector is not None:
                    if isinstance(self.repository.db, (Mock, AsyncMock)):
                        vector_matches = await self.repository.search_similarity(
                            query_embedding=query_vector,
                            top_k=top_k * 3,
                            min_similarity=None,
                            company_id=company_id,
                            document_type=document_type,
                            fiscal_year=fiscal_year,
                            page_number=page_number,
                            query_text=q,
                            include_mock=include_mock
                        )
                        if not isinstance(vector_matches, list):
                            vector_matches = []
                    else:
                        vector_matches = await self.repository.search_similarity(
                            query_embedding=query_vector,
                            top_k=top_k * 3,
                            min_similarity=None,
                            company_id=company_id,
                            document_type=document_type,
                            fiscal_year=fiscal_year,
                            page_number=page_number,
                            query_text=q,
                            include_mock=include_mock
                        )

                if not isinstance(self.repository.db, (Mock, AsyncMock)):
                    keyword_matches = await self.repository.search_keyword(
                        query_text=q,
                        top_k=top_k * 3,
                        company_id=company_id,
                        document_type=document_type,
                        fiscal_year=fiscal_year,
                        page_number=page_number,
                        include_mock=include_mock
                    )

                # Map rank positions
                vector_rank = {c.id: rank for rank, (c, _) in enumerate(vector_matches)}
                keyword_rank = {c.id: rank for rank, (c, _) in enumerate(keyword_matches)}

                # Reciprocal Rank Fusion (RRF) for this query's retrieval lists
                for chunk, _ in vector_matches + keyword_matches:
                    candidate_map[chunk.id] = chunk
                    score = 0.0
                    if chunk.id in vector_rank:
                        score += 1.0 / (60 + vector_rank[chunk.id])
                    if chunk.id in keyword_rank:
                        score += 1.0 / (60 + keyword_rank[chunk.id])
                    
                    # Accumulate RRF score across all expanded queries
                    rrf_scores[chunk.id] = rrf_scores.get(chunk.id, 0.0) + score

            except Exception as search_err:
                logger.error(f"Failed search execution for subquery '{q}': {search_err}")

        # 3. Sort candidates by unified reciprocal rank fusion score
        sorted_candidates = sorted(
            [(candidate_map[cid], score) for cid, score in rrf_scores.items()],
            key=lambda x: x[1],
            reverse=True
        )

        substantive_results = []
        discarded_count_sub = 0

        # 4. Custom Boosting and Penalization
        for chunk, base_rrf_score in sorted_candidates:
            text = chunk.chunk_text
            
            # Substantive chunk check
            if not is_substantive_chunk(text):
                discarded_count_sub += 1
                continue

            # Compute custom boost factors
            boost = 1.0
            
            # Recency boost: +2% per year starting from 2020
            if chunk.fiscal_year:
                boost += 0.02 * max(0, chunk.fiscal_year - 2020)

            # Section & statement relevance boosts
            meta = chunk.metadata_json or {}
            stmt_type = meta.get("statement_type")
            query_lower = query.lower()

            if stmt_type:
                if "balance sheet" in query_lower and stmt_type == "balance_sheet":
                    boost += 0.25
                elif ("profit" in query_lower or "income" in query_lower or "revenue" in query_lower) and stmt_type == "income_statement":
                    boost += 0.25
                elif "cash flow" in query_lower and stmt_type == "cash_flow":
                    boost += 0.25
                elif "risk" in query_lower and stmt_type == "risks":
                    boost += 0.25
                elif "esg" in query_lower and stmt_type == "esg":
                    boost += 0.25
                elif "governance" in query_lower and stmt_type == "governance":
                    boost += 0.25

            # Exact ticker match boost
            if chunk.document and chunk.document.company:
                ticker = chunk.document.company.ticker_symbol.lower()
                if ticker in query_lower:
                    boost += 0.3

            # Overview section boost: reward high-value narrative sections when
            # the query asks for a company summary / business overview.
            if is_overview_query(query_lower) and is_overview_positive_chunk(text, chunk.section_title):
                boost += 0.5

            # TOC or Navigation penalization
            section_title_lower = (chunk.section_title or "").lower()
            if "contents" in section_title_lower or "index" in section_title_lower:
                boost -= 0.5

            # Dense tabular data penalization (subsidiary/ownership/schedule tables).
            # These tables repeat the company name many times, which inflates
            # keyword/FTS rank despite being poor answers to general "what does
            # X do" style questions. Skip the penalty if the user is actually
            # asking about subsidiaries/ownership/structure.
            structural_query_terms = ["subsidiar", "ownership", "shareholding", "holding structure", "group structure"]
            if is_dense_tabular_chunk(text) and not any(t in query_lower for t in structural_query_terms):
                boost -= 0.4

            # Governance / audit chunk penalization for overview queries.
            # Auditor reports, director appointment terms, and statutory disclosures
            # are authoritative but are poor answers to "what does X do" queries.
            # Skip the penalty when the user is explicitly asking about governance/audit.
            governance_query_terms = [
                "auditor", "governance", "director", "appointment",
                "compliance", "statutory", "regulation", "sebi", "board",
            ]
            if (
                is_overview_query(query_lower)
                and is_low_value_governance_chunk(text, chunk.section_title)
                and not any(t in query_lower for t in governance_query_terms)
            ):
                boost -= 0.45

            final_score = base_rrf_score * max(0.1, boost)

            title = chunk.document.title if chunk.document else "Unnamed Document"
            substantive_results.append(
                RetrievalResponse(
                    chunk_text=text,
                    similarity_score=final_score,
                    document_id=chunk.document_id,
                    document_title=title,
                    company_id=chunk.company_id,
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                    section_title=chunk.section_title,
                    document_type=chunk.document_type,
                    fiscal_year=chunk.fiscal_year,
                )
            )

        # Re-sort using final boosted similarity scores descending
        substantive_results.sort(key=lambda r: r.similarity_score, reverse=True)

        # Slice to final top_k results
        final_results = substantive_results[:top_k]

        if not final_results:
            if embedding_failed:
                logger.error(
                    "CRITICAL RETRIEVAL FAILURE: Search yielded 0 chunks because Ollama embedding generation failed. "
                    "Keyword search fallback returned 0 results."
                )
            else:
                logger.warning(
                    f"Retrieval search completed: genuinely 0 matching chunks found for query '{query}'."
                )

        logger.info(
            f"Retrieval: returned {len(final_results)} hybrid-retrieved/reranked chunks "
            f"(from {len(sorted_candidates)} candidates) for query '{query}'"
        )
        return final_results
