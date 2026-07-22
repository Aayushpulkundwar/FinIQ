from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import NewsCategory, NewsSentiment, MarketImpactLevel
from app.repositories.market import MarketRepository
from app.repositories.company import CompanyRepository
from app.services.event_intelligence import EventIntelligenceService
from app.services.response_generation import ResponseGenerationService
from app.schemas.market import (
    NewsArticleOut, MarketAnalyzeResponse, SentimentBreakdown
)


class MarketIntelligenceService:
    """
    MarketIntelligenceService aggregates news articles, correlates them with existing
    Event Intelligence, extracts impacted companies and industries, computes sentiment
    breakdowns, and generates structured market intelligence summaries.

    Does NOT perform news classification or entity extraction — those belong to NewsIntelligenceService.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = MarketRepository(db)
        self.company_repo = CompanyRepository(db)
        self.event_service = EventIntelligenceService(db)
        self.response_generator = ResponseGenerationService()

    async def analyze(
        self,
        company_id: Optional[UUID] = None,
        industry: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 20,
    ) -> MarketAnalyzeResponse:
        """
        Analyze recent market news and generate structured market intelligence.
        """
        from app.core.cache import cache

        # Check cache
        filters_str = f"{company_id}:{industry}:{date_from}:{date_to}:{limit}"
        filters_hash = cache.hash_key(filters_str)
        cache_key = f"market:{filters_hash}"
        
        cached = await cache.get(cache_key)
        if cached is not None:
            logger.info("MarketIntelligenceService: analysis CACHE HIT.")
            return MarketAnalyzeResponse(**cached)

        logger.bind(
            company_id=str(company_id) if company_id else None,
            industry=industry,
        ).info("MarketIntelligenceService: starting analysis.")


        # ── 1. Fetch Market Intel (independent of news articles) ──────────────
        #
        # This runs FIRST so that the Market Intel tab is always populated
        # with live yfinance data regardless of whether any news articles
        # have been ingested for this company yet.
        market_intel_val = None
        try:
            peer_tickers_list: list[str] = []
            db_company = None
            if company_id:
                db_company = await self.company_repo.get(company_id)
                if db_company and db_company.peer_tickers:
                    peer_tickers_list = [
                        t.strip()
                        for t in db_company.peer_tickers.split(",")
                        if t.strip()
                    ]

            if db_company is not None:
                from app.services.market_data import get_market_intel
                ticker_symbol_for_intel = db_company.ticker_symbol
                exchange_for_intel = db_company.exchange
                market_intel_raw = await get_market_intel(
                    ticker_symbol_for_intel, exchange_for_intel, peer_tickers_list
                )
                market_intel_val = market_intel_raw
                logger.info(
                    f"MarketIntelligenceService: market_intel fetched for "
                    f"{ticker_symbol_for_intel} (available={market_intel_raw.get('analyst_consensus', {}).get('available')})"
                )
            else:
                logger.info(
                    "MarketIntelligenceService: no company_id provided, skipping market_intel fetch."
                )
        except Exception as exc:
            logger.warning(f"MarketIntelligenceService: market_intel fetch failed: {exc}")
            market_intel_val = None

        # ── 2. Retrieve Articles ──────────────────────────────────────────────
        articles = await self.repo.get_recent_articles(
            limit=limit,
            company_id=company_id,
            industry=industry,
            date_from=date_from,
            date_to=date_to,
        )

        if not articles:
            logger.warning("MarketIntelligenceService: no articles found for given filters.")
            return MarketAnalyzeResponse(
                market_summary="No news articles available for the specified filters. Please ingest news first.",
                related_news=[],
                related_events=[],
                impacted_companies=[],
                impacted_industries=[],
                sentiment_analysis=SentimentBreakdown(
                    positive_count=0, negative_count=0, neutral_count=0,
                    total=0, overall_sentiment="neutral",
                    positive_pct=0.0, negative_pct=0.0, neutral_pct=0.0
                ),
                supporting_evidence=[],
                market_intel=market_intel_val,
            )

        # ── 3. Compute Sentiment Breakdown ────────────────────────────────────
        pos = sum(1 for a in articles if a.sentiment == NewsSentiment.positive)
        neg = sum(1 for a in articles if a.sentiment == NewsSentiment.negative)
        neu = sum(1 for a in articles if a.sentiment == NewsSentiment.neutral)
        total = len(articles)

        if pos > neg and pos > neu:
            overall = "positive"
        elif neg > pos and neg > neu:
            overall = "negative"
        else:
            overall = "neutral"

        sentiment_breakdown = SentimentBreakdown(
            positive_count=pos,
            negative_count=neg,
            neutral_count=neu,
            total=total,
            overall_sentiment=overall,
            positive_pct=round(pos / total * 100, 1),
            negative_pct=round(neg / total * 100, 1),
            neutral_pct=round(neu / total * 100, 1),
        )

        # ── 4. Extract Impacted Companies and Industries ──────────────────────
        impacted_companies_set: set[str] = set()
        impacted_industries_set: set[str] = set()

        for article in articles:
            # Reload associations in lazy manner via article relationships
            for company_mention in article.company_mentions:
                company = await self.company_repo.get(company_mention.company_id)
                if company:
                    impacted_companies_set.add(company.company_name)
            for industry_mention in article.industry_mentions:
                impacted_industries_set.add(industry_mention.industry_name)

        impacted_companies = sorted(impacted_companies_set)
        impacted_industries = sorted(impacted_industries_set)

        # ── 5. Correlate with Event Intelligence ──────────────────────────────
        related_events: List[str] = []
        if articles:
            # Synthesize a combined topic string from top article titles
            combined_topic = ". ".join(a.title for a in articles[:3])
            try:
                event_result = await self.event_service.analyze(
                    title=f"Market Scan: {combined_topic[:200]}",
                    description=combined_topic
                )
                # Collect correlated event titles from matched companies' evidence
                for ci in event_result.potentially_impacted_companies[:5]:
                    for ev in ci.evidence[:1]:
                        if ev.document_title and ev.document_title not in related_events:
                            related_events.append(ev.document_title)
            except Exception as e:
                logger.warning(f"Event correlation skipped: {e}")

        # ── 6. Persist Grouped MarketEvent ────────────────────────────────────
        dominant_category = _dominant_category(articles)
        impact_level = _compute_impact_level(neg, total)

        try:
            await self.repo.create_market_event({
                "title": f"Market Intelligence Scan — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                "summary": f"Aggregated market event from {total} articles. Overall sentiment: {overall}.",
                "event_type": dominant_category,
                "sentiment": NewsSentiment(overall),
                "impact_level": impact_level,
                "article_count": total,
                "start_date": min(a.published_at for a in articles),
                "end_date": max(a.published_at for a in articles),
            })
            await self.db.commit()
        except Exception as e:
            logger.warning(f"MarketEvent persist skipped: {e}")

        # ── 7. Serialize Articles ─────────────────────────────────────────────
        article_outs = [
            NewsArticleOut(
                id=a.id,
                title=a.title,
                source=a.source,
                url=a.url,
                published_at=a.published_at,
                summary=a.summary,
                category=a.category.value,
                sentiment=a.sentiment.value,
                relevance_score=a.relevance_score,
                confidence_score=a.confidence_score,
                created_at=a.created_at,
            )
            for a in articles
        ]

        # ── 8. Build retrieved_chunks for ResponseGenerationService ──────────
        retrieved_chunks = [
            {
                "chunk_text": a.summary,
                "document_title": f"{a.source} — {a.title}",
                "page_number": 1,
                "section_title": a.category.value,
                "similarity_score": a.relevance_score,
            }
            for a in articles
        ]

        # ── 9. Generate AI Market Summary ────────────────────────────────────
        scope = ""
        if company_id:
            scope = f" for company {company_id}"
        elif industry:
            scope = f" in the {industry} sector"

        query = (
            f"Generate a concise market intelligence summary{scope}. "
            f"Analyzed {total} articles. Overall sentiment: {overall}. "
            f"Key categories: {dominant_category.value}. "
            f"Impacted companies: {', '.join(impacted_companies[:5]) or 'None identified'}. "
            f"Impacted industries: {', '.join(impacted_industries[:5]) or 'None identified'}. "
            f"Provide a structured market overview with risks and opportunities."
        )

        ai_response = await self.response_generator.generate_response(
            user_query=query,
            company_details=None,
            document_metadata=[],
            retrieved_chunks=retrieved_chunks,
        )

        supporting_evidence = list(ai_response.supporting_evidence)[:5]

        # ── 10. Overlay DB Financials onto Peer Comparison (NPM & ROE) ─────────
        #
        # Now that we have market_intel_val from step 1 and DB financials are
        # available, overlay the authoritative DB-stored net_profit_margin and
        # ROE onto the first peer entry (the target company itself) so that
        # the Peer Comparison card reflects audited figures, not just yfinance.
        try:
            if (
                market_intel_val is not None
                and db_company is not None
                and market_intel_val.get("peer_comparison", {}).get("available")
            ):
                from sqlalchemy import select
                from app.models.financial import FinancialPeriod, FinancialMetric
                period_stmt = (
                    select(FinancialPeriod)
                    .where(FinancialPeriod.company_id == company_id)
                    .order_by(FinancialPeriod.fiscal_year.desc())
                    .limit(1)
                )
                period_res = await self.db.execute(period_stmt)
                latest_period = period_res.scalars().first()
                if latest_period:
                    metrics_stmt = select(FinancialMetric).where(
                        FinancialMetric.period_id == latest_period.id
                    )
                    metrics_res = await self.db.execute(metrics_stmt)
                    metrics = metrics_res.scalars().all()
                    db_npm = None
                    db_roe = None
                    for m in metrics:
                        if m.metric_name == "net_profit_margin":
                            db_npm = m.metric_value / 100.0
                        elif m.metric_name == "roe":
                            db_roe = m.metric_value / 100.0

                    peers = market_intel_val["peer_comparison"]["peers"]
                    if peers and peers[0]["ticker"] == db_company.ticker_symbol:
                        if db_npm is not None:
                            peers[0]["net_margin"] = db_npm
                        if db_roe is not None:
                            peers[0]["roe"] = db_roe
        except Exception as exc:
            logger.warning(f"MarketIntelligenceService: DB financials overlay failed: {exc}")

        logger.bind(
            articles_analyzed=total,
            overall_sentiment=overall,
            impacted_companies_count=len(impacted_companies),
        ).info("MarketIntelligenceService: analysis complete.")

        response = MarketAnalyzeResponse(
            market_summary=ai_response.executive_summary,
            related_news=article_outs,
            related_events=related_events,
            impacted_companies=impacted_companies,
            impacted_industries=impacted_industries,
            sentiment_analysis=sentiment_breakdown,
            supporting_evidence=supporting_evidence,
            market_intel=market_intel_val,
        )

        await cache.set(cache_key, response.model_dump(), ttl=3600) # 1h
        return response



# ── Private helpers ───────────────────────────────────────────────────────────

def _dominant_category(articles) -> NewsCategory:
    """Return the most common category across a list of articles."""
    counts: Dict[str, int] = {}
    for a in articles:
        counts[a.category.value] = counts.get(a.category.value, 0) + 1
    best = max(counts, key=counts.get) if counts else "general"
    return NewsCategory(best)


def _compute_impact_level(negative_count: int, total: int) -> MarketImpactLevel:
    """Compute impact level based on negative sentiment ratio."""
    if total == 0:
        return MarketImpactLevel.LOW
    ratio = negative_count / total
    if ratio >= 0.6:
        return MarketImpactLevel.CRITICAL
    elif ratio >= 0.4:
        return MarketImpactLevel.HIGH
    elif ratio >= 0.2:
        return MarketImpactLevel.MEDIUM
    return MarketImpactLevel.LOW
