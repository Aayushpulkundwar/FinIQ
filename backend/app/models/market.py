import uuid
import enum
import hashlib
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, Enum as SQLEnum, ForeignKey, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseModel


class NewsCategory(str, enum.Enum):
    macroeconomic = "macroeconomic"
    regulatory = "regulatory"
    geopolitical = "geopolitical"
    industry = "industry"
    company_specific = "company_specific"
    general = "general"


class NewsSentiment(str, enum.Enum):
    positive = "positive"
    negative = "negative"
    neutral = "neutral"


class MarketImpactLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class NewsArticle(BaseModel):
    """
    SQLAlchemy model representing an ingested financial news article.
    content_hash enables duplicate detection (SHA-256 of title + source + published_at).
    """
    __tablename__ = "news_articles"

    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    raw_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[NewsCategory] = mapped_column(
        SQLEnum(NewsCategory, name="newscategory"), nullable=False, index=True,
        default=NewsCategory.general
    )
    sentiment: Mapped[NewsSentiment] = mapped_column(
        SQLEnum(NewsSentiment, name="newssentiment"), nullable=False, index=True,
        default=NewsSentiment.neutral
    )
    relevance_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # Relationships
    company_mentions = relationship("NewsCompany", back_populates="article", cascade="all, delete-orphan")
    industry_mentions = relationship("NewsIndustry", back_populates="article", cascade="all, delete-orphan")

    @staticmethod
    def compute_hash(title: str, source: str, published_at: str) -> str:
        """Compute SHA-256 hash for deduplication."""
        raw = f"{title.strip().lower()}|{source.strip().lower()}|{str(published_at)}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class NewsCompany(BaseModel):
    """
    Association mapping a NewsArticle to a Company it mentions.
    """
    __tablename__ = "news_companies"

    article_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("news_articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mention_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)

    article = relationship("NewsArticle", back_populates="company_mentions")


class NewsIndustry(BaseModel):
    """
    Association mapping a NewsArticle to an industry sector it mentions.
    """
    __tablename__ = "news_industries"

    article_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("news_articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    industry_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)

    article = relationship("NewsArticle", back_populates="industry_mentions")


class MarketEvent(BaseModel):
    """
    Aggregated market event grouping multiple related news articles into a single market event.
    """
    __tablename__ = "market_events"

    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[NewsCategory] = mapped_column(
        SQLEnum(NewsCategory, name="newscategory"), nullable=False, index=True
    )
    sentiment: Mapped[NewsSentiment] = mapped_column(
        SQLEnum(NewsSentiment, name="newssentiment"), nullable=False, index=True,
        default=NewsSentiment.neutral
    )
    impact_level: Mapped[MarketImpactLevel] = mapped_column(
        SQLEnum(MarketImpactLevel, name="marketimpactlevel"), nullable=False, index=True,
        default=MarketImpactLevel.MEDIUM
    )
    article_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
