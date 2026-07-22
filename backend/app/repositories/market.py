import uuid
from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import NewsArticle, NewsCompany, NewsIndustry, MarketEvent


class MarketRepository:
    """
    Repository layer for all Market Intelligence database operations.
    Handles CRUD for NewsArticle, NewsCompany, NewsIndustry, and MarketEvent models.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── NewsArticle ───────────────────────────────────────────────────────────

    async def get_article_by_hash(self, content_hash: str) -> Optional[NewsArticle]:
        """Lookup an article by its SHA-256 content hash for deduplication."""
        result = await self.db.execute(
            select(NewsArticle).where(NewsArticle.content_hash == content_hash)
        )
        return result.scalar_one_or_none()

    async def create_article(self, data: dict) -> NewsArticle:
        """Persist a new NewsArticle."""
        article = NewsArticle(**data)
        self.db.add(article)
        await self.db.flush()
        return article

    async def get_recent_articles(
        self,
        limit: int = 20,
        company_id: Optional[uuid.UUID] = None,
        industry: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> List[NewsArticle]:
        """
        Retrieve recent news articles with optional filters:
        - company_id: only articles mentioning the specified company
        - industry: only articles mentioning the specified industry name
        - date_from / date_to: published_at range filter
        """
        if company_id is not None:
            # Join via NewsCompany to filter by company
            stmt = (
                select(NewsArticle)
                .join(NewsCompany, NewsCompany.article_id == NewsArticle.id)
                .where(NewsCompany.company_id == company_id)
            )
        elif industry is not None:
            stmt = (
                select(NewsArticle)
                .join(NewsIndustry, NewsIndustry.article_id == NewsArticle.id)
                .where(NewsIndustry.industry_name.ilike(f"%{industry}%"))
            )
        else:
            stmt = select(NewsArticle)

        if date_from:
            stmt = stmt.where(NewsArticle.published_at >= date_from)
        if date_to:
            stmt = stmt.where(NewsArticle.published_at <= date_to)

        stmt = stmt.order_by(NewsArticle.published_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ── NewsCompany ───────────────────────────────────────────────────────────

    async def create_news_company(
        self,
        article_id: uuid.UUID,
        company_id: uuid.UUID,
        mention_count: int = 1,
        confidence: float = 0.8,
    ) -> NewsCompany:
        """Persist a company mention linked to a news article."""
        record = NewsCompany(
            article_id=article_id,
            company_id=company_id,
            mention_count=mention_count,
            confidence=confidence,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    # ── NewsIndustry ──────────────────────────────────────────────────────────

    async def create_news_industry(
        self,
        article_id: uuid.UUID,
        industry_name: str,
        confidence: float = 0.8,
    ) -> NewsIndustry:
        """Persist an industry mention linked to a news article."""
        record = NewsIndustry(
            article_id=article_id,
            industry_name=industry_name,
            confidence=confidence,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    # ── MarketEvent ───────────────────────────────────────────────────────────

    async def create_market_event(self, data: dict) -> MarketEvent:
        """Persist a grouped market event."""
        event = MarketEvent(**data)
        self.db.add(event)
        await self.db.flush()
        return event

    async def get_recent_market_events(self, limit: int = 10) -> List[MarketEvent]:
        """Retrieve the most recently created market events."""
        result = await self.db.execute(
            select(MarketEvent).order_by(MarketEvent.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
