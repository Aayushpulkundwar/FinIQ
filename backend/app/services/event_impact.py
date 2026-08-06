import json
import re
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.core.config import settings
from app.schemas.response_generation import AIResponse
from app.services.base import BaseService
from app.services.retrieval import RetrievalService
from app.services.company import CompanyService
from app.services.unified_news import fetch_harmonized_company_news as fetch_company_news
from app.models.document import DocumentType
from app.core.openrouter_client import openrouter_chat


class EventImpactService(BaseService):
    """
    Service for analyzing how specific macro, geopolitical, or industry events
    impact a company by combining annual report risk factor disclosures
    and topic-scoped APITube news articles via grounded LLM synthesis.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db)
        self.retrieval_service = RetrievalService(db)
        self.company_service = CompanyService(db)

    async def analyze_event_impact(
        self,
        user_query: str,
        company_id: Optional[str] = None,
        ticker_symbol: Optional[str] = None,
    ) -> AIResponse:
        """
        Executes event-impact analysis combining vector search over annual report risk chunks
        and topic-scoped live APITube news search.
        """
        logger.info(f"EventImpactService: Analyzing event impact for query: '{user_query}'")

        # 1. Company Resolution
        company = None
        if company_id:
            try:
                c_uuid = UUID(company_id)
                company = await self.company_service.repository.get(c_uuid)
            except ValueError:
                pass

        if not company and ticker_symbol:
            company = await self.company_service.repository.get_by_ticker(ticker_symbol.upper())

        if not company:
            # Try finding company from query text
            companies = await self.company_service.repository.get_multi()
            for c in companies:
                if c.ticker_symbol.lower() in user_query.lower() or c.company_name.lower() in user_query.lower():
                    company = c
                    break

        company_name = company.company_name if company else "the company"
        ticker = company.ticker_symbol if company else ""

        # 2. Extract Event Topic & Keywords via LLM or Regex Fallback
        extracted = await self._extract_topic_and_keywords(user_query, company_name)
        extracted_topic = extracted["extracted_topic"]
        news_keywords = extracted["news_keywords"]
        annual_report_query = extracted["annual_report_query"]

        logger.info(
            f"EventImpactService: Extracted topic='{extracted_topic}', "
            f"news_keywords={news_keywords}, annual_report_query='{annual_report_query}'"
        )

        # 3. Parallel Retrieval: Annual Report Risk Chunks (min_similarity >= 0.50) + APITube News
        annual_report_chunks = []
        if company:
            try:
                annual_report_chunks = await self.retrieval_service.search(
                    query=annual_report_query,
                    top_k=5,
                    min_similarity=0.50,
                    company_id=company.id,
                    document_type=DocumentType.annual_report,
                )
            except Exception as e_vec:
                logger.warning(f"EventImpactService: Vector search warning: {e_vec}")

        news_articles = []
        if company and news_keywords:
            try:
                news_articles = await fetch_company_news(
                    company_name=company_name,
                    ticker=ticker,
                    limit=10,
                    topic_keywords=news_keywords,
                )
            except Exception as e_news:
                logger.warning(f"EventImpactService: News fetch warning: {e_news}")

        # Filter substantive annual report chunks
        valid_chunks = [c for c in annual_report_chunks if (c.similarity_score or 0) >= 0.50]
        has_chunks = len(valid_chunks) > 0
        has_news = len(news_articles) > 0

        logger.info(f"EventImpactService: Retrieved {len(valid_chunks)} annual report chunks (>=0.50 similarity) and {len(news_articles)} APITube news articles.")

        # 4. Fallback Condition Check: If BOTH return 0 relevant results
        if not has_chunks and not has_news:
            fallback_text = f"No disclosed risk factors or recent news related to this event were found for {company_name}."
            logger.info("EventImpactService: Both retrievals returned 0 relevant items. Returning approved fallback message.")
            return AIResponse(
                executive_summary=fallback_text,
                key_insights=[],
                supporting_evidence=[],
                risks_limitations=[f"No relevant annual report disclosures (similarity >= 0.50) or APITube news articles matched the topic '{extracted_topic}'."],
                sources=[],
                cited_sources_detailed=[],
                provider="finiq_event_analyzer",
                generation_mode="fallback_no_context",
                is_degraded=False,
            )

        # 5. Build Context & LLM Prompt for Grounded Synthesis with Citations
        context_str = self._format_retrieved_context(valid_chunks, news_articles, company_name)
        
        system_prompt = (
            "You are a Senior Financial & Geopolitical Risk Analyst for FinIQ.\n"
            "Synthesize an event-impact report for the user's query based ONLY on the provided context.\n"
            "Context consists of: (1) Disclosed Risk Factors from the Annual Report, and (2) Live APITube News Articles.\n\n"
            "STRICT GROUNDING & CITATION RULES:\n"
            "1. Answer ONLY using facts explicitly stated in the retrieved context. Do NOT speculate or invent information.\n"
            "2. If the retrieved context does NOT contain explicit factual information addressing how the event impacts the company, state clearly in executive_summary: "
            "'No direct annual report disclosures or recent news articles addressing the impact of this event were found in the retrieved context.' "
            "Do NOT assert or speculate ungrounded claims such as 'the company may not be directly impacted' or 'is unlikely to be affected'.\n"
            "3. EVERY factual claim made in executive_summary, key_insights, or supporting_evidence MUST have a corresponding citation in cited_sources_detailed pointing to a retrieved article or annual report chunk. If no citation supports a claim, DO NOT MAKE THE CLAIM.\n"
            "4. If only annual report disclosures exist but no recent news (or vice versa), state this explicitly and do NOT claim the missing source type has information.\n"
            "5. Return ONLY a valid JSON object matching this schema:\n"
            "{\n"
            '  "executive_summary": "2-3 sentence overview based strictly on retrieved facts with inline citations. If context does not address the event, state lack of direct coverage explicitly without speculation.",\n'
            '  "key_insights": ["Insight 1", "Insight 2"],\n'
            '  "supporting_evidence": ["Fact 1 with citation", "Fact 2 with citation"],\n'
            '  "risks_limitations": ["Risk or caveat 1", "Data limitation 2"],\n'
            '  "sources": ["Annual Report 2024 (Page 42, Risk Factors)", "Outlet: Headline - https://..."],\n'
            '  "cited_sources_detailed": [\n'
            '     {"type": "annual_report", "doc_title": "Annual Report 2024", "page": 42, "section": "Risk Factors", "url": null},\n'
            '     {"type": "news", "outlet": "Reuters", "headline": "Headline", "url": "https://...", "published_at": "2026-07-28"}\n'
            '  ]\n'
            "}"
        )

        user_prompt = (
            f"Company: {company_name} ({ticker})\n"
            f"Event Query: {user_query}\n"
            f"Extracted Topic: {extracted_topic}\n\n"
            f"RETRIEVED CONTEXT:\n{context_str}"
        )

        openrouter_key = settings.OPENROUTER_API_KEY
        if not openrouter_key or "placeholder" in openrouter_key.lower():
            # Degraded response format when LLM key is absent
            return self._build_degraded_response(company_name, valid_chunks, news_articles)

        try:
            llm_res = await openrouter_chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                caller_label="EventImpactService.analyze",
            )

            cleaned = llm_res.content.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```json\s*|```$", "", cleaned, flags=re.MULTILINE).strip()

            parsed = json.loads(cleaned)

            raw_sources = parsed.get("sources", [])
            clean_sources = []
            for s in raw_sources:
                if isinstance(s, str):
                    clean_sources.append(s)
                elif isinstance(s, dict):
                    url_part = f" - {s.get('url')}" if s.get('url') else ""
                    clean_sources.append(f"{s.get('outlet') or s.get('doc_title') or 'Source'}: {s.get('headline') or s.get('section') or ''}{url_part}")

            raw_detailed = parsed.get("cited_sources_detailed", [])
            clean_detailed = [d for d in raw_detailed if isinstance(d, dict)]

            exec_summary = parsed.get("executive_summary", "")
            # Guard against ungrounded assertions when 0 citations are provided
            if not clean_detailed and not any(kw in exec_summary.lower() for kw in ["no direct", "no explicit", "no information", "not found", "no relevant"]):
                exec_summary = f"No direct annual report disclosures or recent news articles addressing the impact of '{extracted_topic}' on {company_name} were found in the retrieved context."

            return AIResponse(
                executive_summary=exec_summary,
                key_insights=parsed.get("key_insights", []),
                supporting_evidence=parsed.get("supporting_evidence", []),
                risks_limitations=parsed.get("risks_limitations", []),
                sources=clean_sources,
                cited_sources_detailed=clean_detailed,
                provider=f"openrouter/{llm_res.provider_used}",
                generation_mode="event_impact_synthesis",
                is_degraded=False,
            )

        except Exception as exc:
            logger.error(f"EventImpactService: LLM synthesis failed: {exc}")
            return self._build_degraded_response(company_name, valid_chunks, news_articles)

    async def _extract_topic_and_keywords(self, user_query: str, company_name: str) -> Dict[str, Any]:
        """
        Uses LLM (or regex fallback) to extract the event topic, news keywords,
        and annual report vector query terms.
        """
        openrouter_key = settings.OPENROUTER_API_KEY
        if openrouter_key and "placeholder" not in openrouter_key.lower():
            try:
                system_prompt = (
                    "Extract search parameters from the user's event query about a company. "
                    "Return ONLY a JSON object with keys:\n"
                    '  "is_relevant_event": boolean (true for real geopolitical, macroeconomic, regulatory, supply chain, or industry events; false for absurd/unrelated fictional queries like lunar eclipses or alien invasions),\n'
                    '  "extracted_topic": short string summarizing the event (e.g. "Iran-US war oil price increase"),\n'
                    '  "news_keywords": array of 3-5 specific keyword strings for news search (e.g. ["oil price", "fuel cost", "crude", "Iran", "shipping"]),\n'
                    '  "annual_report_query": string tailored for vector search over annual report risk sections'
                )
                user_prompt = f"Company: {company_name}\nUser Query: {user_query}"
                res = await openrouter_chat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    caller_label="EventImpactService.extract_keywords",
                )
                cleaned = res.content.strip()
                if cleaned.startswith("```"):
                    cleaned = re.sub(r"^```json\s*|```$", "", cleaned, flags=re.MULTILINE).strip()
                parsed = json.loads(cleaned)
                is_rel = parsed.get("is_relevant_event", True)
                return {
                    "extracted_topic": parsed.get("extracted_topic", user_query),
                    "news_keywords": parsed.get("news_keywords", []) if is_rel else [],
                    "annual_report_query": parsed.get("annual_report_query", user_query) if is_rel else "risk factors non_existent_topic",
                }
            except Exception as e:
                logger.warning(f"EventImpactService: Keyword extraction LLM call failed: {e}")

        # Deterministic Regex Fallback
        clean_q = re.sub(r"(?i)\b(how has the|how does|what is the impact of|affected|affect|impact|on|for)\b", "", user_query).strip()
        words = [w for w in clean_q.split() if len(w) > 2 and w.lower() not in company_name.lower()]
        return {
            "extracted_topic": clean_q or user_query,
            "news_keywords": words[:5],
            "annual_report_query": f"risk factors {' '.join(words[:5])}",
        }

    def _format_retrieved_context(self, chunks: List[Any], articles: List[Any], company_name: str) -> str:
        parts = []
        if chunks:
            parts.append("=== ANNUAL REPORT RISK DISCLOSURES ===")
            for idx, c in enumerate(chunks, 1):
                doc_title = getattr(c, "document_title", None) or f"{company_name} Annual Report"
                page = getattr(c, "page_number", 1)
                section = getattr(c, "section_title", "Risk Factors")
                text = getattr(c, "chunk_text", str(c))
                parts.append(f"[Annual Report Chunk {idx}] Document: {doc_title} | Page: {page} | Section: {section}\nContent: {text}\n")
        else:
            parts.append("=== ANNUAL REPORT RISK DISCLOSURES ===\nNo relevant annual report risk disclosures found (similarity < 0.50).\n")

        if articles:
            parts.append("=== LIVE APITUBE NEWS ARTICLES ===")
            for idx, art in enumerate(articles, 1):
                title = getattr(art, "title", "Untitled")
                source = getattr(art, "source", "APITube")
                url = getattr(art, "url", "")
                pub = getattr(art, "published_at", "")
                snippet = getattr(art, "snippet", "")
                parts.append(f"[News Article {idx}] Title: {title} | Source: {source} | URL: {url} | Date: {pub}\nSnippet: {snippet}\n")
        else:
            parts.append("=== LIVE APITUBE NEWS ARTICLES ===\nNo recent news articles found for this topic.\n")

        return "\n".join(parts)

    def _build_degraded_response(self, company_name: str, chunks: List[Any], articles: List[Any]) -> AIResponse:
        evidence = []
        sources = []
        detailed = []

        for c in chunks:
            doc_title = getattr(c, "document_title", None) or f"{company_name} Annual Report"
            page = getattr(c, "page_number", 1)
            section = getattr(c, "section_title", "Risk Factors")
            evidence.append(f"Annual Report Disclosure: {getattr(c, 'chunk_text', '')[:180]}...")
            sources.append(f"{doc_title} (Page {page}, {section})")
            detailed.append({
                "type": "annual_report",
                "doc_title": doc_title,
                "page": page,
                "section": section,
                "url": None
            })

        for art in articles:
            title = getattr(art, "title", "")
            source = getattr(art, "source", "")
            url = getattr(art, "url", "")
            pub = str(getattr(art, "published_at", ""))[:10]
            evidence.append(f"News Article ({source}): {title}")
            sources.append(f"{source}: {title} ({pub}) - {url}")
            detailed.append({
                "type": "news",
                "outlet": source,
                "headline": title,
                "url": url,
                "published_at": pub
            })

        summary = f"Retrieved {len(chunks)} annual report risk disclosures and {len(articles)} news articles for {company_name}."
        return AIResponse(
            executive_summary=summary,
            key_insights=[f"Retrieved {len(chunks)} annual report risk sections", f"Retrieved {len(articles)} live news articles"],
            supporting_evidence=evidence,
            risks_limitations=["Response generated in fallback mode."],
            sources=sources,
            cited_sources_detailed=detailed,
            provider="finiq_event_analyzer",
            generation_mode="event_impact_degraded",
            is_degraded=True,
        )
