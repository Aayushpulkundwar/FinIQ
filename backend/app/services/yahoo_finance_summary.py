"""
Yahoo Finance Financial Summary Service
=======================================
Fetches Revenue, EBITDA, Net Profit, and ROE for a company from Yahoo Finance
using yfinance, using the most recently available fiscal year.

Follows the same async + thread-pool + Redis caching pattern as market_data.py.

Field sourcing strategy
------------------------
Revenue     → income_stmt["Total Revenue"]
EBITDA      → income_stmt["EBITDA"]  or  Operating Income + D&A (calculated)
Net Profit  → income_stmt["Net Income"]  or  info["netIncomeToCommon"] (fallback)
ROE         → info["returnOnEquity"]  or  Net Income / avg(Stockholders Equity) (calculated)

Source labels
-------------
Each field returns a companion *_source key:
  "yahoo_direct"  – value came straight from a yfinance DataFrame cell
  "calculated"    – value was derived from other available fields
  None            – value could not be determined at all
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> Optional[float]:
    """Convert a value to float, returning None on failure."""
    try:
        v = float(value)
        import math
        return None if math.isnan(v) or math.isinf(v) else v
    except (TypeError, ValueError):
        return None


def _get_row(df, *candidate_names: str) -> Optional[Any]:
    """
    Return the first row in a DataFrame whose index label matches one of
    the candidate_names (case-insensitive substring match).
    Returns the raw Series or None.
    """
    if df is None or df.empty:
        return None
    idx_lower = {str(i).lower(): i for i in df.index}
    for name in candidate_names:
        for key_lower, key_orig in idx_lower.items():
            if name.lower() in key_lower:
                return df.loc[key_orig]
    return None


def _first_value(series) -> Optional[float]:
    """Return the most recent (first column) numeric value from a Series."""
    if series is None:
        return None
    try:
        return _safe_float(series.iloc[0])
    except (IndexError, AttributeError):
        return None


def _build_unavailable(ticker: str, reason: str) -> Dict[str, Any]:
    return {
        "ticker": ticker,
        "available": False,
        "reason": reason,
        "fiscal_year": None,
        "currency": None,
        "revenue": None,
        "revenue_source": None,
        "ebitda": None,
        "ebitda_source": None,
        "net_profit": None,
        "net_profit_source": None,
        "roe": None,
        "roe_source": None,
    }


# ---------------------------------------------------------------------------
# Core synchronous fetch (runs in thread-pool)
# ---------------------------------------------------------------------------

def _fetch_financial_summary_sync(yf_ticker: str) -> Dict[str, Any]:
    """
    Blocking yfinance call.  Executed via asyncio.run_in_executor so it does
    not block the FastAPI event loop.
    """
    try:
        import yfinance as yf

        # yfinance >= 1.5.1 uses curl_cffi Chrome impersonation by default;
        # do NOT pass session= as it breaks financial-statement fetches.
        ticker_obj = yf.Ticker(yf_ticker)

        # ── Pull raw DataFrames ──────────────────────────────────────────
        try:
            income = ticker_obj.income_stmt          # annual
        except Exception:
            income = None

        try:
            balance = ticker_obj.balance_sheet
        except Exception:
            balance = None

        try:
            info: Dict[str, Any] = ticker_obj.info or {}
        except Exception:
            info = {}

        # ── Determine fiscal year from most recent column ─────────────────
        fiscal_year_label: Optional[str] = None
        if income is not None and not income.empty and len(income.columns) > 0:
            latest_col = income.columns[0]           # pandas Timestamp
            try:
                fiscal_year_label = f"FY{latest_col.year}"
            except AttributeError:
                fiscal_year_label = str(latest_col)[:4]
        elif balance is not None and not balance.empty and len(balance.columns) > 0:
            latest_col = balance.columns[0]
            try:
                fiscal_year_label = f"FY{latest_col.year}"
            except AttributeError:
                fiscal_year_label = str(latest_col)[:4]

        if fiscal_year_label is None:
            # If we have absolutely no data, bail out
            return _build_unavailable(yf_ticker, "No financial statement data available on Yahoo Finance.")

        currency: Optional[str] = info.get("currency") or info.get("financialCurrency") or "INR"

        # ── Revenue ───────────────────────────────────────────────────────
        revenue: Optional[float] = None
        revenue_source: Optional[str] = None

        rev_row = _get_row(income, "total revenue", "totalrevenue")
        revenue = _first_value(rev_row)
        if revenue is not None:
            revenue_source = "yahoo_direct"
            logger.debug(f"[{yf_ticker}] Revenue: {revenue} (yahoo_direct)")
        else:
            logger.warning(f"[{yf_ticker}] Revenue not found in income_stmt")

        # ── EBITDA ────────────────────────────────────────────────────────
        ebitda: Optional[float] = None
        ebitda_source: Optional[str] = None

        ebitda_row = _get_row(income, "ebitda")
        ebitda = _first_value(ebitda_row)
        if ebitda is not None:
            ebitda_source = "yahoo_direct"
            logger.debug(f"[{yf_ticker}] EBITDA: {ebitda} (yahoo_direct)")
        else:
            # Fallback: Operating Income + D&A
            oper_row = _get_row(income, "operating income", "ebit")
            da_row   = _get_row(income, "depreciation", "reconciled depreciation", "d&a")
            oper     = _first_value(oper_row)
            da       = _first_value(da_row)
            if oper is not None and da is not None:
                ebitda = oper + da
                ebitda_source = "calculated"
                logger.debug(f"[{yf_ticker}] EBITDA: {ebitda} (calculated from OperIncome={oper} + D&A={da})")
            elif oper is not None:
                # Partial: use operating income as a proxy (no D&A)
                ebitda = oper
                ebitda_source = "calculated"
                logger.warning(f"[{yf_ticker}] EBITDA: using Operating Income only (D&A unavailable)")
            else:
                logger.warning(f"[{yf_ticker}] EBITDA could not be calculated")

        # ── Net Profit ────────────────────────────────────────────────────
        net_profit: Optional[float] = None
        net_profit_source: Optional[str] = None

        ni_row = _get_row(income, "net income", "net profit", "netincome")
        net_profit = _first_value(ni_row)
        if net_profit is not None:
            net_profit_source = "yahoo_direct"
            logger.debug(f"[{yf_ticker}] Net Profit: {net_profit} (yahoo_direct)")
        else:
            # Fallback: info dict
            ni_info = _safe_float(info.get("netIncomeToCommon"))
            if ni_info is not None:
                net_profit = ni_info
                net_profit_source = "calculated"
                logger.debug(f"[{yf_ticker}] Net Profit: {net_profit} (from info['netIncomeToCommon'])")
            else:
                logger.warning(f"[{yf_ticker}] Net Profit not found")

        # ── ROE ───────────────────────────────────────────────────────────
        roe: Optional[float] = None
        roe_source: Optional[str] = None

        # First attempt: info dict (trailing twelve months)
        roe_info = _safe_float(info.get("returnOnEquity"))
        if roe_info is not None:
            roe = roe_info
            roe_source = "yahoo_direct"
            logger.debug(f"[{yf_ticker}] ROE: {roe} (yahoo_direct from info)")
        else:
            # Manual: Net Income / avg(Stockholders Equity)
            eq_row = _get_row(balance, "stockholders equity", "total equity", "common stock equity",
                              "shareholders equity")
            if eq_row is not None and net_profit is not None:
                equity_current = _first_value(eq_row)
                # Try prior year if available
                equity_prior: Optional[float] = None
                try:
                    equity_prior = _safe_float(eq_row.iloc[1])
                except (IndexError, AttributeError):
                    pass

                if equity_current is not None and equity_current != 0:
                    if equity_prior is not None:
                        avg_equity = (equity_current + equity_prior) / 2.0
                    else:
                        avg_equity = equity_current
                    roe = net_profit / avg_equity
                    roe_source = "calculated"
                    logger.debug(f"[{yf_ticker}] ROE: {roe:.4f} (calculated, avg_equity={avg_equity})")
            if roe is None:
                logger.warning(f"[{yf_ticker}] ROE could not be calculated")

        return {
            "ticker": yf_ticker,
            "available": True,
            "reason": None,
            "fiscal_year": fiscal_year_label,
            "currency": currency,
            "revenue": revenue,
            "revenue_source": revenue_source,
            "ebitda": ebitda,
            "ebitda_source": ebitda_source,
            "net_profit": net_profit,
            "net_profit_source": net_profit_source,
            "roe": roe,
            "roe_source": roe_source,
        }

    except Exception as exc:
        logger.warning(f"[{yf_ticker}] yfinance financial summary fetch failed: {exc}")
        return _build_unavailable(yf_ticker, f"yfinance error: {exc}")


# ---------------------------------------------------------------------------
# Public async entry point
# ---------------------------------------------------------------------------

async def get_financial_summary(ticker_symbol: str, exchange: str = "") -> Dict[str, Any]:
    """
    Async wrapper: resolves the correct yfinance ticker for *ticker_symbol* on
    *exchange*, checks Redis, then fetches from Yahoo Finance if needed.

    Parameters
    ----------
    ticker_symbol : str
        Raw ticker as stored in the DB (e.g. ``ARVIND``).
    exchange : str
        Exchange name (e.g. ``NSE``). Used to append the correct yfinance suffix.

    Returns
    -------
    dict
        Always returns a dict. Sets ``available=False`` with a ``reason`` string
        on any failure — never raises.
    """
    from app.core.cache import cache
    # Reuse the resolver from market_data to stay DRY
    from app.services.market_data import _resolve_ticker

    yf_ticker = _resolve_ticker(ticker_symbol, exchange)
    cache_key = f"financial_summary:{yf_ticker}"
    TTL_SUCCESS = 28_800   # 8 hours
    TTL_FAILURE = 60       # 1 minute — retry quickly on transient failures

    # --- Cache check ---
    cached = await cache.get(cache_key)
    if cached is not None:
        logger.debug(f"financial_summary cache HIT: {cache_key}")
        return cached

    # --- Fetch (non-blocking) ---
    logger.info(f"Fetching financial summary for {yf_ticker} via yfinance (exchange={exchange!r})")
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _fetch_financial_summary_sync, yf_ticker)

    # --- Cache result ---
    await cache.set(cache_key, data, ttl=TTL_SUCCESS if data["available"] else TTL_FAILURE)

    return data
