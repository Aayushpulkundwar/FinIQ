from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class NewsIngestionRequest(BaseModel):
    """Request schema for ingesting a single financial news article."""
    title: str = Field(..., description="Article headline")
    source: str = Field(..., description="Publication source (e.g. Reuters, Bloomberg)")
    url: Optional[str] = Field(None, description="Article URL")
    published_at: datetime = Field(..., description="Publication timestamp (UTC)")
    summary: str = Field(..., description="Article summary or lead paragraph")
    raw_content: Optional[str] = Field(None, description="Full article body text (optional)")


class NewsArticleOut(BaseModel):
    """Serialized news article returned by the API."""
    id: UUID
    title: str
    source: str
    url: Optional[str]
    published_at: datetime
    summary: str
    category: str
    sentiment: str
    relevance_score: float
    confidence_score: float
    created_at: datetime

    class Config:
        from_attributes = True


class NewsIngestionResponse(BaseModel):
    """Response after ingesting a single news article."""
    article_id: UUID
    title: str
    category: str
    sentiment: str
    relevance_score: float
    confidence_score: float
    extracted_companies: List[str] = Field(default_factory=list)
    extracted_industries: List[str] = Field(default_factory=list)
    is_duplicate: bool = Field(default=False)


class MarketAnalyzeRequest(BaseModel):
    """Request schema for market intelligence analysis."""
    company_id: Optional[UUID] = Field(None, description="Filter by company UUID")
    industry: Optional[str] = Field(None, description="Filter by industry name")
    date_from: Optional[datetime] = Field(None, description="Start of date range")
    date_to: Optional[datetime] = Field(None, description="End of date range")
    limit: int = Field(default=20, ge=1, le=100, description="Max articles to analyze")


class SentimentBreakdown(BaseModel):
    """Breakdown of sentiment scores across analyzed news articles."""
    positive_count: int
    negative_count: int
    neutral_count: int
    total: int
    overall_sentiment: str
    positive_pct: float
    negative_pct: float
    neutral_pct: float



class AnalystConsensus(BaseModel):
    """Analyst opinion and targets consensus."""
    available: bool
    reason: Optional[str] = None
    recommendation_key: Optional[str] = None
    recommendation_mean: Optional[float] = None
    target_mean_price: Optional[float] = None
    target_high_price: Optional[float] = None
    target_low_price: Optional[float] = None
    target_median_price: Optional[float] = None
    number_of_analyst_opinions: Optional[int] = None


class InstitutionalHolder(BaseModel):
    """Ownership stake held by an institution."""
    holder: str
    shares: Optional[int] = None
    date_reported: Optional[str] = None
    pct_out: Optional[float] = None
    value: Optional[float] = None


class OwnershipStructure(BaseModel):
    """Insider and institutional ownership breakdowns."""
    available: bool
    reason: Optional[str] = None
    held_percent_institutions: Optional[float] = None
    held_percent_insiders: Optional[float] = None
    top_institutional_holders: List[InstitutionalHolder] = Field(default_factory=list)
    major_holders_breakdown: Dict[str, Any] = Field(default_factory=dict)


class TradingMomentum(BaseModel):
    """Trading activity, short interest, and moving average deltas."""
    available: bool
    reason: Optional[str] = None
    short_percent_of_float: Optional[float] = None
    shares_short: Optional[int] = None
    short_ratio: Optional[float] = None
    fifty_day_average: Optional[float] = None
    two_hundred_day_average: Optional[float] = None
    beta: Optional[float] = None
    price_vs_fifty_day_pct: Optional[float] = None
    price_vs_two_hundred_day_pct: Optional[float] = None


class PeerMetric(BaseModel):
    """Basic valuation and profit margins for a peer company."""
    ticker: str
    pe_ratio: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    roe: Optional[float] = None


class PeerComparison(BaseModel):
    """Side-by-side metric comparisons with similar companies."""
    available: bool
    reason: Optional[str] = None
    peers: List[PeerMetric] = Field(default_factory=list)


class MarketIntelResponse(BaseModel):
    """Consolidated market intelligence structure for the UI tab."""
    ticker: str
    currency: str
    current_price: Optional[float] = None
    analyst_consensus: AnalystConsensus
    ownership: OwnershipStructure
    trading_momentum: TradingMomentum
    peer_comparison: PeerComparison
    as_of: str


class MarketAnalyzeResponse(BaseModel):
    """Full market intelligence analysis response."""
    market_summary: str = Field(..., description="AI-generated market summary paragraph")
    related_news: List[NewsArticleOut] = Field(default_factory=list)
    related_events: List[str] = Field(default_factory=list, description="Correlated event titles")
    impacted_companies: List[str] = Field(default_factory=list)
    impacted_industries: List[str] = Field(default_factory=list)
    sentiment_analysis: SentimentBreakdown
    supporting_evidence: List[str] = Field(default_factory=list)
    market_intel: Optional[MarketIntelResponse] = None
