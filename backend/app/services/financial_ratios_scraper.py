"""
Financial Ratios Scraper Service
=================================
Standalone dedicated scraper service for fetching financial ratios (ROE, Margins, YoY Growth)
directly from Yahoo Finance via yfinance.

ALL ratio values in FinancialRatios are explicitly normalized to final display-ready
percentages on a 0-100 scale (e.g. roe_percent = 5.62 for 5.62%, NOT 0.0562).
Callers must NEVER multiply or divide returned values by 100.
"""
import asyncio
import math
from datetime import datetime, timezone
from typing import Any, Optional, Dict
from pydantic import BaseModel, Field
from loguru import logger

from app.services.market_data import _resolve_ticker


class FinancialRatios(BaseModel):
    """
    Structured financial ratios and growth metrics directly sourced from yfinance.
    
    IMPORTANT CONVENTION:
    All ratio and growth fields in this schema are expressed as FINAL DISPLAY-READY PERCENTAGES
    on a 0-100 scale (e.g. roe_percent = 5.62 for 5.62%, NOT a 0.0562 decimal fraction).
    No caller or UI component should multiply or divide by 100.
    """
    ticker: str
    available: bool = True
    reason: Optional[str] = None
    
    # Financial Ratios (Percentages 0-100%)
    roe_percent: Optional[float] = Field(None, description="Return on Equity in % (e.g. 5.62 for 5.62%)")
    net_margin_percent: Optional[float] = Field(None, description="Net Profit Margin in % (e.g. 1.04 for 1.04%)")
    gross_margin_percent: Optional[float] = Field(None, description="Gross Profit Margin in % (e.g. 15.08 for 15.08%)")
    operating_margin_percent: Optional[float] = Field(None, description="Operating Margin in % (e.g. 2.80 for 2.80%)")
    
    # YoY Growth Metrics (Percentages 0-100%)
    revenue_growth_yoy_percent: Optional[float] = Field(None, description="YoY Revenue Growth in % (e.g. 10.09 for 10.09%)")
    ebitda_growth_yoy_percent: Optional[float] = Field(None, description="YoY EBITDA Growth in %")
    net_profit_growth_yoy_percent: Optional[float] = Field(None, description="YoY Net Profit Growth in %")
    
    currency: Optional[str] = None
    as_of: Optional[str] = None


def normalize_percentage(val: Any, input_scale: str = "fraction") -> Optional[float]:
    """
    Safely normalizes numeric percentage metrics to a standard 0-100 scale.

    Parameters
    ----------
    val : Any
        Raw numeric value (e.g., 0.0562 or 5.62).
    input_scale : str ('fraction' | 'percent')
        - 'fraction': raw decimal fraction scale where 0.0562 represents 5.62%.
        - 'percent': already on 0-100 percentage scale (e.g. 5.62).

    Returns
    -------
    Optional[float]
        Normalized percentage value on a 0-100 scale (e.g. 5.62), or None.
    """
    if val is None:
        return None
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return None
        if input_scale == "fraction":
            if abs(v) <= 2.0 and v != 0:
                return round(v * 100.0, 2)
            return round(v, 2)
        elif input_scale == "percent":
            return round(v, 2)
        else:
            if abs(v) <= 2.0 and v != 0:
                return round(v * 100.0, 2)
            return round(v, 2)
    except (TypeError, ValueError):
        return None


def _to_percent(val: Any) -> Optional[float]:
    """Legacy alias for normalize_percentage(val, input_scale='fraction')."""
    return normalize_percentage(val, input_scale="fraction")


def _fetch_financial_ratios_sync(yf_ticker: str) -> FinancialRatios:
    """
    Synchronous blocking fetch from yfinance. Executed via thread-pool executor.
    Returns FinancialRatios schema with all percentages on 0-100 scale.
    """
    try:
        import yfinance as yf
        ticker_obj = yf.Ticker(yf_ticker)
        
        info: Dict[str, Any] = ticker_obj.info or {}
        if not info or not info.get("symbol"):
            # Check if income statement exists as fallback indicator
            try:
                inc = ticker_obj.income_stmt
                if inc is None or inc.empty:
                    return FinancialRatios(
                        ticker=yf_ticker,
                        available=False,
                        reason=f"Ticker '{yf_ticker}' not found or market data unavailable on Yahoo Finance."
                    )
            except Exception:
                return FinancialRatios(
                    ticker=yf_ticker,
                    available=False,
                    reason=f"Ticker '{yf_ticker}' not found on Yahoo Finance."
                )

        currency = info.get("currency") or info.get("financialCurrency") or "USD"

        # Direct yfinance ratio fields
        roe = _to_percent(info.get("returnOnEquity"))
        net_margin = _to_percent(info.get("profitMargins"))
        gross_margin = _to_percent(info.get("grossMargins"))
        operating_margin = _to_percent(info.get("operatingMargins"))
        
        # YoY Revenue Growth
        rev_growth = _to_percent(info.get("revenueGrowth"))
        ebitda_growth = None
        net_profit_growth = _to_percent(info.get("earningsGrowth"))

        # Fallback calculation for growth rates if direct info dict lacks them
        try:
            inc = ticker_obj.income_stmt
            if inc is not None and not inc.empty and len(inc.columns) >= 2:
                idx_lower = {str(i).lower(): i for i in inc.index}
                
                # Revenue YoY fallback
                if rev_growth is None:
                    rev_key = next((k for k in idx_lower if "total revenue" in k or "totalrevenue" in k), None)
                    if rev_key:
                        s = inc.loc[idx_lower[rev_key]]
                        r0, r1 = _to_percent(s.iloc[0]), _to_percent(s.iloc[1])
                        if r0 is not None and r1 is not None and r1 != 0:
                            rev_growth = round(((s.iloc[0] - s.iloc[1]) / abs(s.iloc[1])) * 100.0, 2)

                # EBITDA YoY fallback
                ebitda_key = next((k for k in idx_lower if "ebitda" in k), None)
                if ebitda_key:
                    s = inc.loc[idx_lower[ebitda_key]]
                    if len(s) >= 2 and s.iloc[1] and s.iloc[1] != 0:
                        ebitda_growth = round(((s.iloc[0] - s.iloc[1]) / abs(s.iloc[1])) * 100.0, 2)

                # Net profit YoY fallback
                if net_profit_growth is None:
                    ni_key = next((k for k in idx_lower if "net income" in k or "netincome" in k), None)
                    if ni_key:
                        s = inc.loc[idx_lower[ni_key]]
                        if len(s) >= 2 and s.iloc[1] and s.iloc[1] != 0:
                            net_profit_growth = round(((s.iloc[0] - s.iloc[1]) / abs(s.iloc[1])) * 100.0, 2)
        except Exception as exc:
            logger.debug(f"[{yf_ticker}] Financial statement YoY growth fallback calculation failed: {exc}")

        # Check if at least one metric is available
        if all(v is None for v in [roe, net_margin, gross_margin, operating_margin, rev_growth]):
            return FinancialRatios(
                ticker=yf_ticker,
                available=False,
                reason=f"No financial ratio metrics reported for '{yf_ticker}' on Yahoo Finance.",
                currency=currency,
            )

        return FinancialRatios(
            ticker=yf_ticker,
            available=True,
            reason=None,
            roe_percent=roe,
            net_margin_percent=net_margin,
            gross_margin_percent=gross_margin,
            operating_margin_percent=operating_margin,
            revenue_growth_yoy_percent=rev_growth,
            ebitda_growth_yoy_percent=ebitda_growth,
            net_profit_growth_yoy_percent=net_profit_growth,
            currency=currency,
            as_of=datetime.now(timezone.utc).isoformat().replace("+00:00", "") + "Z",
        )
    except Exception as exc:
        logger.error(f"Failed to fetch financial ratios for {yf_ticker}: {exc}")
        return FinancialRatios(
            ticker=yf_ticker,
            available=False,
            reason=f"Scraper error for ticker {yf_ticker}: {str(exc)}"
        )


async def fetch_financial_ratios(ticker: str, exchange: str = "") -> FinancialRatios:
    """
    Async public entry point to scrape financial ratios for a given company ticker & exchange.
    Executes yfinance fetch via thread-pool executor to prevent blocking the event loop.
    Returns FinancialRatios with all percentage metrics on 0-100 scale.
    """
    yf_ticker = _resolve_ticker(ticker, exchange)
    logger.info(f"Fetching financial ratios via scraper for {yf_ticker} (ticker={ticker!r}, exchange={exchange!r})")
    
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, _fetch_financial_ratios_sync, yf_ticker)
    return res
