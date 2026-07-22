"""
Schemas for the Yahoo Finance financial summary and recommendation endpoints.
"""
from typing import Literal, Optional
from pydantic import BaseModel


class FinancialSummaryResponse(BaseModel):
    """
    Response schema for GET /api/v1/companies/{id}/financial-summary.

    Fields
    ------
    ticker          : Fully-qualified yfinance ticker (e.g. 'ARVIND.NS')
    available       : False when Yahoo Finance returned no usable data
    reason          : Human-readable explanation when available=False
    fiscal_year     : Label of the most recent fiscal year (e.g. 'FY2025')
    currency        : ISO currency code reported by Yahoo (e.g. 'INR', 'USD')
    revenue         : Total Revenue in base currency units (no scaling)
    ebitda          : EBITDA (direct or calculated)
    net_profit      : Net Income
    roe             : Return on Equity as a decimal (e.g. 0.18 = 18%)
    *_source        : 'yahoo_direct' | 'calculated' | None per field
    """
    ticker: str
    available: bool
    reason: Optional[str] = None
    fiscal_year: Optional[str] = None
    currency: Optional[str] = None
    revenue: Optional[float] = None
    revenue_source: Optional[str] = None
    ebitda: Optional[float] = None
    ebitda_source: Optional[str] = None
    net_profit: Optional[float] = None
    net_profit_source: Optional[str] = None
    roe: Optional[float] = None
    roe_source: Optional[str] = None


class RecommendationResponse(BaseModel):
    """
    Response schema for GET /api/v1/companies/{id}/recommendation.

    Fields
    ------
    signal          : 'Buy' | 'Sell' | 'Hold' | 'Unavailable'
    current_price   : Live price from Yahoo Finance (None when Unavailable)
    intrinsic_value : DCF intrinsic value per share (None when Unavailable)
    upside_pct      : ((intrinsic - current) / current) * 100 (None when Unavailable)
    currency        : ISO currency code (e.g. 'INR', 'USD') (None when Unavailable)
    reason          : Short code explaining why signal is Unavailable, e.g.
                      'insufficient_data' | 'data_fetch_failed'. Only present
                      when signal == 'Unavailable'.
    """
    signal: Literal["Buy", "Sell", "Hold", "Unavailable"]
    current_price: Optional[float] = None
    intrinsic_value: Optional[float] = None
    upside_pct: Optional[float] = None
    currency: Optional[str] = None
    reason: Optional[str] = None
    wacc: Optional[float] = None
    terminal_growth_rate: Optional[float] = None
