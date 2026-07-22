import re
from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import NewsArticle, NewsCategory, NewsSentiment
from app.repositories.market import MarketRepository
from app.repositories.company import CompanyRepository
from app.schemas.market import NewsIngestionRequest, NewsIngestionResponse


# ── Classification keyword maps ──────────────────────────────────────────────

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    NewsCategory.macroeconomic: [
        "gdp", "inflation", "interest rate", "federal reserve", "fed", "monetary policy",
        "central bank", "rbi", "recession", "unemployment", "economic growth", "cpi",
        "consumer price", "yield curve", "quantitative easing", "fiscal policy",
        "trade deficit", "current account", "forex", "exchange rate",
    ],
    NewsCategory.regulatory: [
        "regulation", "compliance", "sec", "sebi", "regulatory", "fine", "penalty",
        "antitrust", "investigation", "lawsuit", "litigation", "court", "enforcement",
        "legislation", "bill", "act", "law", "directive", "compliance framework",
    ],
    NewsCategory.geopolitical: [
        "geopolitical", "war", "conflict", "sanction", "tariff", "trade war", "embargo",
        "nato", "ukraine", "russia", "china", "taiwan", "middle east", "election",
        "political", "government", "ministry", "minister", "president",
    ],
    NewsCategory.industry: [
        "sector", "industry", "market share", "supply chain", "disruption", "technology",
        "semiconductor", "pharma", "energy", "oil", "renewable", "auto", "banking",
        "fintech", "healthcare", "manufacturing", "retail", "real estate",
    ],
    NewsCategory.company_specific: [
        "earnings", "revenue", "profit", "loss", "quarterly", "annual report",
        "merger", "acquisition", "ipo", "dividend", "buyback", "ceo", "cfo",
        "management", "guidance", "forecast", "analyst", "upgrade", "downgrade",
    ],
}

_POSITIVE_WORDS = [
    "growth", "surge", "rise", "gain", "profit", "beat", "record", "strong",
    "positive", "outperform", "upgrade", "expansion", "recovery", "rally",
    "bullish", "success", "opportunity", "boost", "increase", "improved",
]

_NEGATIVE_WORDS = [
    "decline", "fall", "drop", "loss", "miss", "weak", "concern", "risk",
    "negative", "underperform", "downgrade", "contraction", "recession",
    "bearish", "crisis", "warning", "cut", "lower", "decrease", "slowdown",
    "default", "bankruptcy", "shutdown", "layoff", "reduce",
]

_INDUSTRY_KEYWORDS = {
    "Technology": ["tech", "software", "ai", "semiconductor", "cloud", "digital", "cybersecurity"],
    "Banking & Finance": ["bank", "finance", "financial", "insurance", "fintech", "credit"],
    "Energy": ["oil", "gas", "energy", "renewable", "solar", "wind", "power"],
    "Healthcare": ["pharma", "biotech", "healthcare", "drug", "medical", "hospital"],
    "Automotive": ["auto", "electric vehicle", "ev", "car", "automobile"],
    "Retail": ["retail", "consumer", "e-commerce", "shopping", "fmcg"],
    "Real Estate": ["real estate", "property", "realty", "reit", "construction"],
    "Manufacturing": ["manufacturing", "industrial", "steel", "aluminium", "cement"],
    "Telecom": ["telecom", "5g", "spectrum", "mobile", "wireless"],
    "Agriculture": ["agri", "agriculture", "food", "crop", "commodity"],
}


class NewsIntelligenceService:
    """
    NewsIntelligenceService handles:
    - Ingesting news articles (via API payload, not live scraping)
    - Classifying articles into categories via keyword matching
    - Assigning positive/negative/neutral sentiment
    - Extracting mentioned company tickers and industry sectors
    - Deduplicating articles using SHA-256 content hash
    - Scoring relevance (category confidence) and confidence (entity extraction)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = MarketRepository(db)
        self.company_repo = CompanyRepository(db)

    async def ingest(self, request: NewsIngestionRequest) -> NewsIngestionResponse:
        """
        Ingest a single news article, classify it, extract entities, and persist.
        Returns NewsIngestionResponse with extracted metadata.
        """
        # 1. Compute dedup hash
        content_hash = NewsArticle.compute_hash(
            title=request.title,
            source=request.source,
            published_at=str(request.published_at)
        )

        # 2. Duplicate check
        existing = await self.repo.get_article_by_hash(content_hash)
        if existing:
            logger.bind(title=request.title).info("NewsIntelligenceService: duplicate article detected, skipping.")
            return NewsIngestionResponse(
                article_id=existing.id,
                title=existing.title,
                category=existing.category.value,
                sentiment=existing.sentiment.value,
                relevance_score=existing.relevance_score,
                confidence_score=existing.confidence_score,
                is_duplicate=True
            )

        # 3. Classify category
        full_text = f"{request.title} {request.summary} {request.raw_content or ''}"
        category, category_confidence = self._classify_category(full_text)

        # 4. Classify sentiment
        sentiment = self._classify_sentiment(full_text)

        # 5. Extract companies (by ticker mention)
        extracted_tickers = self._extract_tickers(full_text)

        # 6. Extract industries
        extracted_industries = self._extract_industries(full_text)

        # 7. Compute relevance score based on category confidence + entity richness
        entity_bonus = min(0.2, (len(extracted_tickers) + len(extracted_industries)) * 0.03)
        relevance_score = round(min(1.0, category_confidence + entity_bonus), 3)
        confidence_score = round(category_confidence, 3)

        # 8. Persist article
        article_data = {
            "title": request.title,
            "source": request.source,
            "url": request.url,
            "published_at": request.published_at,
            "summary": request.summary,
            "raw_content": request.raw_content,
            "category": category,
            "sentiment": sentiment,
            "relevance_score": relevance_score,
            "confidence_score": confidence_score,
            "content_hash": content_hash,
        }
        article = await self.repo.create_article(article_data)

        # 9. Persist company mentions (resolve tickers to company IDs)
        matched_companies: List[str] = []
        for ticker in extracted_tickers:
            company = await self.company_repo.get_by_ticker(ticker)
            if company:
                await self.repo.create_news_company(
                    article_id=article.id,
                    company_id=company.id,
                    mention_count=full_text.lower().count(ticker.lower()),
                    confidence=0.85,
                )
                matched_companies.append(company.company_name)

        # 10. Persist industry mentions
        for industry_name in extracted_industries:
            await self.repo.create_news_industry(
                article_id=article.id,
                industry_name=industry_name,
                confidence=0.80,
            )

        await self.db.commit()

        logger.bind(
            article_id=str(article.id), category=category.value,
            sentiment=sentiment.value, companies=matched_companies,
            industries=extracted_industries
        ).info("NewsIntelligenceService: article ingested successfully.")

        return NewsIngestionResponse(
            article_id=article.id,
            title=article.title,
            category=category.value,
            sentiment=sentiment.value,
            relevance_score=relevance_score,
            confidence_score=confidence_score,
            extracted_companies=matched_companies,
            extracted_industries=list(extracted_industries),
            is_duplicate=False,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _classify_category(self, text: str) -> Tuple[NewsCategory, float]:
        """Classify article using keyword matching, return (category, confidence)."""
        text_lower = text.lower()
        scores: dict[str, int] = {cat.value: 0 for cat in NewsCategory}

        for category, keywords in _CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    scores[category.value] += 1

        best_cat = max(scores, key=scores.get)
        best_score = scores[best_cat]
        total_keywords = sum(len(v) for v in _CATEGORY_KEYWORDS.values())
        confidence = round(min(1.0, 0.4 + (best_score / total_keywords) * 4), 3)

        if best_score == 0:
            return NewsCategory.general, 0.4
        return NewsCategory(best_cat), confidence

    def _classify_sentiment(self, text: str) -> NewsSentiment:
        """Rule-based sentiment classification using positive/negative keyword counts."""
        text_lower = text.lower()
        pos = sum(1 for w in _POSITIVE_WORDS if w in text_lower)
        neg = sum(1 for w in _NEGATIVE_WORDS if w in text_lower)
        if pos > neg:
            return NewsSentiment.positive
        elif neg > pos:
            return NewsSentiment.negative
        return NewsSentiment.neutral

    def _extract_tickers(self, text: str) -> List[str]:
        """Extract likely stock ticker symbols (2-5 uppercase letters) from article text."""
        raw_tickers = re.findall(r"\b[A-Z]{2,5}\b", text)
        # Filter out common English words (stop words) that match uppercase pattern
        stop_words = {
            "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN", "HER",
            "WAS", "ONE", "OUR", "OUT", "SAY", "SHE", "WHO", "DID", "ITS", "LET",
            "NOW", "GET", "USE", "TWO", "WAY", "MAY", "NEW", "OLD", "SEE", "HIM",
            "HIS", "HOW", "DAY", "HAS", "MAN", "SET", "PUT", "END", "WHY", "TRY",
            "US", "UK", "EU", "UN", "GDP", "CPI", "IPO", "CEO", "CFO", "COO",
            "SEC", "RBI", "FED", "IMF", "WTO", "ETF", "EPS", "AI", "IT", "PE"
        }
        return list({t for t in raw_tickers if t not in stop_words})[:8]

    def _extract_industries(self, text: str) -> List[str]:
        """Match industry keywords against article text to extract mentioned sectors."""
        text_lower = text.lower()
        matched = []
        for industry_name, keywords in _INDUSTRY_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                matched.append(industry_name)
        return matched
