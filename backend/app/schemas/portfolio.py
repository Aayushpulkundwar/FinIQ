from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class WatchlistCreate(BaseModel):
    """Schema for watchlist creation."""
    name: str = Field(..., max_length=100, description="Watchlist name")


class WatchlistAddCompany(BaseModel):
    """Schema for adding a company to a watchlist."""
    company_id: UUID = Field(..., description="Company UUID")


class WatchlistItemOut(BaseModel):
    """Schema representing a company list item in a watchlist."""
    id: UUID
    company_id: UUID
    company_name: str
    ticker_symbol: str

    class Config:
        from_attributes = True


class WatchlistOut(BaseModel):
    """Watchlist detail response."""
    id: UUID
    name: str
    user_id: UUID
    items: List[WatchlistItemOut] = Field(default_factory=list)
    created_at: datetime

    class Config:
        from_attributes = True


class PortfolioCreate(BaseModel):
    """Schema for portfolio creation."""
    name: str = Field(..., max_length=100, description="Portfolio name")


class HoldingCreate(BaseModel):
    """Schema for adding a portfolio holding."""
    company_id: UUID = Field(..., description="Company UUID")
    shares: float = Field(..., gt=0, description="Number of shares purchased")
    average_cost: float = Field(..., gt=0, description="Purchase price per share")


class HoldingOut(BaseModel):
    """Holding detail response."""
    id: UUID
    company_id: UUID
    company_name: str
    ticker_symbol: str
    shares: float
    average_cost: float
    current_price: float = Field(..., description="Latest share price based on corporate valuation calculations")
    market_value: float = Field(..., description="Current value of holdings")
    total_gain_loss: float = Field(..., description="Gain/loss amount")
    pnl_pct: float = Field(..., description="Percentage return")

    class Config:
        from_attributes = True


class PortfolioOut(BaseModel):
    """Portfolio detail response."""
    id: UUID
    name: str
    user_id: UUID
    holdings: List[HoldingOut] = Field(default_factory=list)
    total_market_value: float = Field(0.0)
    total_cost_basis: float = Field(0.0)
    total_gain_loss: float = Field(0.0)
    pnl_pct: float = Field(0.0)
    created_at: datetime

    class Config:
        from_attributes = True


class AllocationItem(BaseModel):
    """Breakdown percentage for a specific company or sector in a portfolio."""
    label: str
    value: float
    percentage: float


class PortfolioAnalysisResponse(BaseModel):
    """Diversification, allocation, and risk metrics response."""
    portfolio_id: UUID
    portfolio_name: str
    total_market_value: float
    allocation_by_company: List[AllocationItem] = Field(default_factory=list)
    allocation_by_sector: List[AllocationItem] = Field(default_factory=list)
    risk_score: float = Field(..., description="Calculated portfolio risk score between 1.0 (Low) and 10.0 (High)")
    diversification_status: str = Field(..., description="AI evaluation of diversification health (e.g. Well Diversified, Concentrated)")


class PortfolioRecommendationResponse(BaseModel):
    """AI recommendations for portfolio optimization and balance adjustments."""
    portfolio_id: UUID
    recommendations: str = Field(..., description="AI-generated investment rebalancing recommendations")
    suggested_allocations: List[AllocationItem] = Field(default_factory=list)
