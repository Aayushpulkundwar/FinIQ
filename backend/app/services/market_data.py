"""
Market Data Service
===================
Fetches real-time market data from Yahoo Finance via yfinance for companies
listed on any supported exchange. The correct Yahoo Finance ticker suffix is
derived from the ``exchange`` field stored in the ``companies`` table.

Supported exchange → suffix mapping
-------------------------------------
Exchange   | DB value   | yfinance suffix | Example
-----------|------------|-----------------|------------------
NSE        | NSE        | .NS             | ARVIND.NS
BSE        | BSE        | .BO             | ARVIND.BO
NASDAQ     | NASDAQ     | (none)          | MSFT
NYSE       | NYSE       | (none)          | JPM
LSE        | LSE        | .L              | HSBA.L
TSX        | TSX        | .TO             | RY.TO
ASX        | ASX        | .AX             | BHP.AX

Results are Redis-cached with a 90-second TTL on success (15 s on failure)
to respect Yahoo Finance rate limits.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import pandas as pd

from loguru import logger


import re

# ---------------------------------------------------------------------------
# Exchange → yfinance suffix table
# ---------------------------------------------------------------------------

# Keys are normalised to uppercase; values are appended directly to the ticker.
_EXCHANGE_SUFFIX: dict[str, str] = {
    "NSE":    ".NS",   # National Stock Exchange (India)
    "BSE":    ".BO",   # Bombay Stock Exchange (India)
    "NASDAQ": "",      # NASDAQ (USA)
    "NYSE":   "",      # New York Stock Exchange (USA)
    "LSE":    ".L",    # London Stock Exchange (UK)
    "TSX":    ".TO",   # Toronto Stock Exchange (Canada)
    "ASX":    ".AX",   # Australian Securities Exchange
}


def _resolve_ticker(ticker_symbol: str, exchange: str) -> str:
    """
    Return the fully-qualified yfinance ticker for *ticker_symbol* on *exchange*.
    Tokenizes composite exchange strings (e.g. 'NSE, BSE', 'BSE/NSE', 'nse, bse')
    and matches individual tokens against _EXCHANGE_SUFFIX (prioritizing NSE -> .NS).
    Falls back gracefully with a warning if no token matches.
    """
    if not ticker_symbol:
        return ""

    ticker_upper = ticker_symbol.strip().upper()
    # Avoid duplicate suffixing if ticker already contains a known suffix
    for suf in _EXCHANGE_SUFFIX.values():
        if suf and ticker_upper.endswith(suf):
            return ticker_upper

    exchange_raw = (exchange or "").strip()
    if not exchange_raw:
        return ticker_upper

    # Tokenize exchange string by commas, slashes, and whitespace
    tokens = [t.strip().upper() for t in re.split(r"[,\s/]+", exchange_raw) if t.strip()]

    # Match tokens against _EXCHANGE_SUFFIX (prioritizing NSE if present)
    matched_suffix = None
    for token in tokens:
        if token in _EXCHANGE_SUFFIX:
            matched_suffix = _EXCHANGE_SUFFIX[token]
            if token == "NSE":
                break

    if matched_suffix is not None:
        return f"{ticker_upper}{matched_suffix}"

    logger.warning(
        f"Unknown exchange string '{exchange}' (tokens={tokens}) for ticker '{ticker_symbol}'. "
        "Attempting raw ticker (no suffix)."
    )
    return ticker_upper


# ---------------------------------------------------------------------------
# Anti-bot session factory
# ---------------------------------------------------------------------------

def _get_yf_session():
    """
    Return a browser-impersonating session for yfinance.

    NOTE: yfinance >= 1.5.1 ships with curl_cffi as its built-in session and
    uses Chrome impersonation by default — you do NOT need to pass session=
    to yf.Ticker() for anti-bot protection.  This factory is kept for
    forward-compatibility and explicit use in external HTTP calls, but should
    NOT be passed to yf.Ticker() as doing so can interfere with yfinance's
    internal session management and break financial-statement fetches.

    curl_cffi impersonates Chrome at the TLS/HTTP fingerprint level, which
    bypasses Yahoo's anti-bot layer more reliably than header-only spoofing.
    If curl_cffi is unavailable, fall back to a plain requests.Session with
    realistic browser headers (lower reliability).
    """
    try:
        from curl_cffi import requests as cffi_requests  # type: ignore
        return cffi_requests.Session(impersonate="chrome")
    except Exception:  # noqa: BLE001
        # Fallback: header-only spoofing — less reliable against Yahoo's
        # current anti-bot measures but better than nothing.
        import requests as _requests
        session = _requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        })
        return session


# ---------------------------------------------------------------------------
# Response schema helpers
# ---------------------------------------------------------------------------

def _build_unavailable(ticker: str, reason: str) -> Dict[str, Any]:
    """Return a standardised 'unavailable' payload instead of raising."""
    return {
        "ticker": ticker,
        "available": False,
        "reason": reason,
        "current_price": None,
        "currency": None,
        "market_cap": None,
        "day_change_pct": None,
        "day_change_abs": None,
        "previous_close": None,
        "week_52_high": None,
        "week_52_low": None,
        "pe_ratio": None,
        "volume": None,
        "avg_volume": None,
    }


def _fetch_yfinance_sync(yf_ticker: str) -> Dict[str, Any]:
    """
    Blocking yfinance call – executed in a thread-pool so we don't block the
    FastAPI event loop.
    """
    try:
        import yfinance as yf

        # yfinance >= 1.5.1 uses curl_cffi Chrome impersonation by default;
        # do NOT pass session= as it breaks financial-statement fetches.
        ticker_obj = yf.Ticker(yf_ticker)
        info: Dict[str, Any] = ticker_obj.info or {}

        # Detect missing / stale ticker (Yahoo returns a minimal dict when unknown)
        current_price = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
        )
        if current_price is None:
            return _build_unavailable(
                yf_ticker, "Ticker not found or market data unavailable on Yahoo Finance."
            )

        previous_close: Optional[float] = (
            info.get("regularMarketPreviousClose") or info.get("previousClose")
        )
        day_change_abs: Optional[float] = None
        day_change_pct: Optional[float] = None
        if current_price is not None and previous_close:
            day_change_abs = round(current_price - previous_close, 2)
            day_change_pct = round((day_change_abs / previous_close) * 100, 2)

        # Use the currency yfinance reports — never assume INR or USD
        currency: str = info.get("currency") or "USD"

        return {
            "ticker": yf_ticker,
            "available": True,
            "reason": None,
            "current_price": round(float(current_price), 2),
            "currency": currency,
            "market_cap": info.get("marketCap"),
            "day_change_pct": day_change_pct,
            "day_change_abs": day_change_abs,
            "previous_close": round(float(previous_close), 2) if previous_close else None,
            "week_52_high": info.get("fiftyTwoWeekHigh"),
            "week_52_low": info.get("fiftyTwoWeekLow"),
            "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
            "volume": info.get("regularMarketVolume") or info.get("volume"),
            "avg_volume": info.get("averageVolume"),
        }

    except Exception as exc:
        logger.warning(f"yfinance fetch failed for {yf_ticker}: {exc}")
        return _build_unavailable(yf_ticker, f"yfinance error: {exc}")


# ---------------------------------------------------------------------------
# Public async entry point
# ---------------------------------------------------------------------------

async def get_market_data(ticker_symbol: str, exchange: str = "") -> Dict[str, Any]:
    """
    Async wrapper: resolves the correct yfinance ticker for *ticker_symbol* on
    *exchange*, checks Redis, then fetches from Yahoo Finance if needed.

    Parameters
    ----------
    ticker_symbol : str
        Raw ticker as stored in the DB (e.g. ``MSFT``, ``ARVIND``).
    exchange : str
        Exchange name as stored in the DB (e.g. ``NASDAQ``, ``NSE``).
        Used to determine the correct yfinance suffix.

    Returns
    -------
    dict
        Always returns a dict. Sets ``available=False`` with a ``reason``
        string on any failure — never raises.
    """
    from app.core.cache import cache

    yf_ticker = _resolve_ticker(ticker_symbol, exchange)
    cache_key = f"market_data:{yf_ticker}"
    cache_ttl = 90  # seconds

    # --- Cache check ---
    cached = await cache.get(cache_key)
    if cached is not None:
        logger.debug(f"market_data cache HIT: {cache_key}")
        return cached

    # --- Fetch from Yahoo Finance (run in thread-pool, non-blocking) ---
    logger.info(f"Fetching live market data for {yf_ticker} via yfinance (exchange={exchange!r})")
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _fetch_yfinance_sync, yf_ticker)

    # --- Cache result ---
    await cache.set(cache_key, data, ttl=cache_ttl if data["available"] else 15)

    return data


# ---------------------------------------------------------------------------
# DCF inputs fetcher for live recommendation
# ---------------------------------------------------------------------------

def _get_row_value(df, *candidate_names: str) -> Optional[float]:
    """
    Return the first value in a DataFrame whose index label matches one of
    the candidate_names (case-insensitive substring match).
    """
    if df is None or df.empty:
        return None
    import pandas as pd
    idx_lower = {str(i).lower(): i for i in df.index}
    for name in candidate_names:
        for key_lower, key_orig in idx_lower.items():
            if name.lower() in key_lower:
                val = df.loc[key_orig]
                if isinstance(val, pd.Series):
                    try:
                        return float(val.iloc[0])
                    except (IndexError, AttributeError, TypeError, ValueError):
                        return None
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return None
    return None


def _fetch_dcf_inputs_sync(yf_ticker: str) -> dict:
    """
    Blocking yfinance call to gather DCF-relevant fundamentals based on UFCF.
    """
    try:
        import yfinance as yf

        # yfinance >= 1.5.1 uses curl_cffi Chrome impersonation by default;
        # do NOT pass session= as it breaks financial-statement fetches.
        ticker_obj = yf.Ticker(yf_ticker)
        info: dict = ticker_obj.info or {}

        current_price = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
        )
        if current_price is None:
            return {
                "available": False,
                "reason": "Valuation unavailable",
                "missing": "current_price",
            }

        # ── Pull raw DataFrames ──────────────────────────────────────────
        try:
            inc = ticker_obj.income_stmt
        except Exception:
            inc = None

        try:
            cf = ticker_obj.cashflow
        except Exception:
            cf = None

        try:
            bal = ticker_obj.balance_sheet
        except Exception:
            bal = None

        # FCF directly from Cash Flow Statement (first candidate)
        fcf = _get_row_value(cf, "free cash flow")

        # EBIT (operating_income)
        ebit = _get_row_value(inc, "operating income", "ebit")
        if ebit is None:
            pretax = _get_row_value(inc, "pretax income", "pre-tax income", "income before tax")
            interest = _get_row_value(inc, "interest expense", "interest expense non operating")
            if pretax is not None and interest is not None:
                ebit = pretax + interest
                logger.info(f"EBIT was missing for {yf_ticker}, derived from Pretax Income + Interest Expense: {ebit}")
        
        # Depreciation & Amortization
        dep = _get_row_value(cf, "depreciation amortization depletion", "depreciation and amortization", "depreciation")
        if dep is None:
            ebitda = _get_row_value(inc, "ebitda", "normalized ebitda")
            if ebitda is not None and ebit is not None:
                dep = ebitda - ebit
                if dep < 0:
                    dep = 0.0
                logger.info(f"Depreciation was missing for {yf_ticker}, derived from EBITDA - EBIT: {dep}")
        
        # CapEx (always positive)
        capex = _get_row_value(cf, "capital expenditure", "purchase of ppe")
        if capex is not None:
            capex = abs(capex)
        else:
            # Fallback to Investing Cash Flow
            investing_cf = _get_row_value(cf, "investing cash flow", "net cash flows from investing activities", "net cash used in investing activities")
            if investing_cf is not None:
                capex = abs(investing_cf)
                logger.info(f"CapEx was missing for {yf_ticker}, derived from Investing Cash Flow: {capex}")

        # Net Profit and EBITDA for sanity checks
        net_profit = _get_row_value(inc, "net income", "net profit", "net income continuous operations")
        ebitda = _get_row_value(inc, "ebitda", "normalized ebitda")

        # Change in Working Capital
        wcap = _get_row_value(cf, "change in working capital", "changes in working capital")
        if wcap is None:
            ocf = _get_row_value(cf, "operating cash flow")
            if net_profit is not None and ocf is not None:
                dep_val = dep if dep is not None else 0.0
                wcap = float(net_profit) + dep_val - float(ocf)
                logger.info(f"Change in Working Capital was missing for {yf_ticker}, derived from Net Income + Dep - OCF: {wcap}")

        # Cash
        cash = info.get("totalCash")
        if cash is None:
            cash = _get_row_value(bal, "cash and cash equivalents", "cash equivalents", "cash cash equivalents and short term investments")
        if cash is None:
            cash = 0.0

        # Debt
        debt = info.get("totalDebt")
        if debt is None:
            debt = _get_row_value(bal, "total debt", "long term debt", "longterm debt")
        if debt is None:
            debt = 0.0

        # Shares outstanding (normalise and verify)
        shares_outstanding = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
        if not shares_outstanding:
            shares_outstanding = _get_row_value(bal, "shares outstanding", "diluted shares outstanding", "ordinary shares number", "share issued")

        # Tax Rate (default to 25% for Indian tickers, 21% for others)
        pretax_income = _get_row_value(inc, "pretax income", "pre-tax income", "income before tax")
        tax_provision = _get_row_value(inc, "tax provision", "income tax expense", "tax expense")
        
        tax_rate = None
        tax_rate_estimated = False
        if pretax_income and tax_provision and pretax_income > 0:
            calculated_tax_rate = tax_provision / pretax_income
            if 0.0 <= calculated_tax_rate <= 0.6:
                tax_rate = calculated_tax_rate
                logger.info(f"Estimated Tax Rate from Income Statement for {yf_ticker}: {tax_rate:.2%}")
        
        if tax_rate is None:
            tax_rate = 0.25 if yf_ticker.endswith(".NS") or yf_ticker.endswith(".BO") else 0.21
            tax_rate_estimated = True
            logger.info(f"Tax Rate unavailable for {yf_ticker}, defaulted to: {tax_rate:.2%}")

        # Cost of Debt
        interest_expense = _get_row_value(inc, "interest expense", "interest expense non operating", "interest expense non-operating")
        if interest_expense is not None:
            interest_expense = abs(interest_expense)

        cost_of_debt = None
        cost_of_debt_estimated = False
        if interest_expense is not None and debt > 0:
            raw_cost_of_debt = interest_expense / debt
            if 0.01 <= raw_cost_of_debt <= 0.25:
                cost_of_debt = raw_cost_of_debt
            else:
                cost_of_debt = 0.06
                cost_of_debt_estimated = True
        else:
            cost_of_debt = 0.06
            cost_of_debt_estimated = True

        # Fetch risk-free rate (^TNX)
        risk_free_rate = 0.040
        try:
            tnx_ticker = yf.Ticker("^TNX")
            tnx_hist = tnx_ticker.history(period="1d")
            if not tnx_hist.empty:
                risk_free_rate = float(tnx_hist["Close"].iloc[-1]) / 100.0
                logger.info(f"Live Risk-Free Rate (^TNX): {risk_free_rate:.4%}")
            else:
                logger.warning("Empty history for ^TNX, using 4% fallback")
        except Exception as exc:
            logger.warning(f"Failed to fetch live risk-free rate (^TNX): {exc}, using 4% fallback")

        # Beta validation and fallback
        raw_beta_from_yf = info.get("beta")
        yf_sector = info.get("sector")
        from app.services.valuation_utils import validate_beta
        beta, beta_source = validate_beta(raw_beta_from_yf, yf_sector)
        logger.info(
            f"[TEMPORARY DIAGNOSTIC] RAW YFINANCE FETCH:\n"
            f"  - Ticker: {yf_ticker}\n"
            f"  - info['beta']: {raw_beta_from_yf} (type: {type(raw_beta_from_yf)})\n"
            f"  - info['longName']: {info.get('longName')}\n"
            f"  - info['marketCap']: {info.get('marketCap')}"
        )
        logger.info(f"Beta validation for {yf_ticker}: raw={raw_beta_from_yf}, resolved={beta}, source={beta_source}")

        # Choose / Compute FCF
        baseline_fcf = None
        ufcf_computed = None
        
        # We calculate UFCF as fallback (only if EBIT and other critical items are available)
        if ebit is not None and dep is not None and capex is not None and wcap is not None:
            ufcf_computed = ebit * (1 - tax_rate) + dep - capex - wcap

        if fcf is not None and fcf > 0:
            baseline_fcf = fcf
            logger.info(f"Using direct Free Cash Flow ({baseline_fcf}) as baseline FCF for {yf_ticker}.")
        elif ufcf_computed is not None:
            baseline_fcf = ufcf_computed
            logger.info(f"Direct FCF is unavailable or non-positive. Using computed UFCF ({baseline_fcf}) as baseline FCF for {yf_ticker}.")

        # Log detailed intermediate valuation inputs before performing validation checks
        logger.info(
            f"DCF Intermediate Valuation Inputs for {yf_ticker}:\n"
            f"  - Free Cash Flow (Direct): {fcf}\n"
            f"  - computed UFCF: {ufcf_computed}\n"
            f"  - Selected Baseline FCF: {baseline_fcf}\n"
            f"  - EBIT: {ebit}\n"
            f"  - Depreciation: {dep}\n"
            f"  - CapEx: {capex}\n"
            f"  - Change in Working Capital: {wcap}\n"
            f"  - Cash & Cash Equivalents: {cash}\n"
            f"  - Total Debt: {debt}\n"
            f"  - Shares Outstanding: {shares_outstanding}\n"
            f"  - Tax Rate: {tax_rate}"
        )

        # Validate critical derived inputs: shares_outstanding, current_price, baseline_fcf, cash, debt
        missing_inputs = []
        if current_price is None or current_price <= 0:
            missing_inputs.append("current_price")
        if shares_outstanding is None or shares_outstanding <= 0:
            missing_inputs.append("shares_outstanding")
        if baseline_fcf is None or baseline_fcf <= 0:
            missing_inputs.append("free_cash_flow/ufcf (must be positive)")

        if missing_inputs:
            logger.warning(
                f"Recommendation unavailable for {yf_ticker}. Critical inputs could not be derived after fallbacks. "
                f"Missing: {', '.join(missing_inputs)}. Details: "
                f"ebit={ebit}, dep={dep}, capex={capex}, wcap={wcap}, cash={cash}, debt={debt}, shares={shares_outstanding}, tax_rate={tax_rate}"
            )
            return {
                "available": False,
                "reason": "Valuation unavailable",
                "missing": f"Missing: {', '.join(missing_inputs)}",
            }

        # Verify shares outstanding against market cap
        mcap = info.get("marketCap")
        if mcap and current_price and shares_outstanding:
            calculated_mcap = current_price * shares_outstanding
            deviation = abs(mcap - calculated_mcap) / mcap
            if deviation > 0.05:
                logger.warning(
                    f"Shares outstanding deviation exceeds 5% for {yf_ticker}: "
                    f"Market Cap={mcap}, Calculated Market Cap={calculated_mcap} "
                    f"(Price={current_price}, Shares={shares_outstanding}), Deviation={deviation:.2%}"
                )

        # Calculate historical FCF CAGR projection rate
        fcf_history = []
        if cf is not None and not cf.empty:
            # We need the full multi-year Series, NOT a single float; use direct
            # index lookup (case-insensitive) rather than _get_row_value which
            # collapses the row to a scalar.
            idx_lower = {str(i).lower(): i for i in cf.index}
            row_series_fcf = None
            for name in ("free cash flow",):
                for key_lower, key_orig in idx_lower.items():
                    if name in key_lower:
                        row_series_fcf = cf.loc[key_orig]
                        break
                if row_series_fcf is not None:
                    break

            if row_series_fcf is None:
                # Fallback: Operating Cash Flow - CapEx (also as full Series)
                row_series_ocf, row_series_capex = None, None
                for key_lower, key_orig in idx_lower.items():
                    if "operating cash flow" in key_lower:
                        row_series_ocf = cf.loc[key_orig]
                    if "capital expenditure" in key_lower:
                        row_series_capex = cf.loc[key_orig]
                if row_series_ocf is not None and row_series_capex is not None:
                    row_series_fcf = row_series_ocf - row_series_capex.abs()

            if row_series_fcf is not None and isinstance(row_series_fcf, pd.Series):
                valid_fcf = row_series_fcf.dropna()
                valid_fcf = valid_fcf.sort_index()  # Oldest first
                fcf_history = [float(v) for v in valid_fcf.values]

        fcf_growth_rate = None
        fcf_growth_estimated = False
        fcf_growth_source = "default fallback"

        if len(fcf_history) >= 2:
            fcf_oldest = fcf_history[0]
            fcf_newest = fcf_history[-1]
            n_years = len(fcf_history) - 1
            if fcf_oldest > 0 and fcf_newest > 0:
                try:
                    cagr = (fcf_newest / fcf_oldest) ** (1.0 / n_years) - 1.0
                    # Bound FCF growth rate to a reasonable range
                    if -0.15 <= cagr <= 0.35:
                        fcf_growth_rate = cagr
                        fcf_growth_source = "historical FCF CAGR"
                        logger.info(f"Calculated historical FCF CAGR for {yf_ticker}: {cagr:.2%}")
                except Exception as e:
                    logger.warning(f"Error calculating CAGR: {e}")

        if fcf_growth_rate is None:
            rev_growth = info.get("revenueGrowth")
            if rev_growth is not None:
                try:
                    fcf_growth_rate = float(rev_growth)
                    fcf_growth_estimated = True
                    fcf_growth_source = "analyst revenue growth estimate"
                    logger.info(f"Using analyst revenue growth estimate for {yf_ticker}: {fcf_growth_rate:.2%}")
                except (TypeError, ValueError):
                    pass

        if fcf_growth_rate is None:
            fcf_growth_rate = 0.08
            fcf_growth_estimated = True
            fcf_growth_source = "default fallback"
            logger.info(f"FCF growth unavailable, using 8% default for {yf_ticker}")

        # Bound final FCF growth rate
        fcf_growth_rate = max(-0.10, min(0.25, fcf_growth_rate))

        currency = info.get("currency") or "USD"

        return {
            "available": True,
            "reason": None,
            "current_price": round(float(current_price), 2),
            "free_cash_flow": float(baseline_fcf),
            "shares_outstanding": float(shares_outstanding),
            "fcf_growth_rate": fcf_growth_rate,
            "currency": currency,
            "cash": float(cash),
            "debt": float(debt),
            "ebit": float(ebit) if ebit is not None else 0.0,
            "depreciation": float(dep) if dep is not None else 0.0,
            "capex": float(capex) if capex is not None else 0.0,
            "change_in_working_capital": float(wcap) if wcap is not None else 0.0,
            "tax_rate": float(tax_rate),
            "net_profit": float(net_profit) if net_profit is not None else None,
            "ebitda": float(ebitda) if ebitda is not None else None,
            "beta": beta,
            "beta_source": beta_source,
            "risk_free_rate": risk_free_rate,
            "cost_of_debt": cost_of_debt,
            "cost_of_debt_estimated": cost_of_debt_estimated,
            "tax_rate_estimated": tax_rate_estimated,
            "fcf_growth_estimated": fcf_growth_estimated,
            "fcf_growth_source": fcf_growth_source,
            "market_cap": float(mcap) if mcap else (current_price * shares_outstanding),
        }

    except Exception as exc:
        logger.warning(f"DCF inputs fetch failed for {yf_ticker}: {exc}")
        return {
            "available": False,
            "reason": "data_fetch_failed",
            "missing": str(exc),
        }


async def get_yfinance_dcf_inputs(ticker_symbol: str, exchange: str = "") -> dict:
    """
    Async wrapper: fetches DCF-relevant fundamentals for a ticker from
    Yahoo Finance via a thread-pool executor (non-blocking).

    Results are Redis-cached with a long TTL on success (financials don't
    change intraday) and a short TTL on failure to allow retries without
    re-hammering Yahoo.

    Always returns a dict.  Sets available=False with a reason string
    on any failure — never raises.
    """
    from app.core.cache import cache

    yf_ticker = _resolve_ticker(ticker_symbol, exchange)
    cache_key = f"dcf_inputs:v2:{yf_ticker}"

    cached = await cache.get(cache_key)
    if cached is not None:
        logger.debug(f"dcf_inputs cache HIT: {cache_key}")
        return cached

    loop = asyncio.get_event_loop()
    try:
        data = await asyncio.wait_for(
            loop.run_in_executor(None, _fetch_dcf_inputs_sync, yf_ticker),
            timeout=20.0
        )
    except asyncio.TimeoutError:
        logger.warning(f"DCF inputs fetch timed out for {yf_ticker}")
        data = {
            "available": False,
            "reason": "timeout",
            "missing": "Yahoo Finance did not respond in time",
        }

    # Longer TTL on success (financials don't change intraday),
    # short TTL on failure to allow retry without re-hammering Yahoo.
    await cache.set(cache_key, data, ttl=1800 if data.get("available") else 30)

    return data


# ---------------------------------------------------------------------------
# Market Intelligence / Tab Fetchers
# ---------------------------------------------------------------------------

def _fetch_peer_metrics_sync(yf_ticker: str) -> Dict[str, Any]:
    """Blocking yfinance call to retrieve core margins and PE for a peer company."""
    try:
        import yfinance as yf
        ticker_obj = yf.Ticker(yf_ticker)
        info = ticker_obj.info or {}
        return {
            "ticker": yf_ticker.split(".")[0],
            "pe_ratio": info.get("trailingPE"),
            "gross_margin": info.get("grossMargins"),
            "operating_margin": info.get("operatingMargins"),
            "net_margin": info.get("profitMargins"),
            "roe": info.get("returnOnEquity"),
        }
    except Exception as exc:
        logger.warning(f"Failed to fetch peer metrics for {yf_ticker}: {exc}")
        return {
            "ticker": yf_ticker.split(".")[0],
            "pe_ratio": None,
            "gross_margin": None,
            "operating_margin": None,
            "net_margin": None,
            "roe": None,
        }


def _fetch_market_intel_sync(yf_ticker: str) -> Dict[str, Any]:
    """Blocking yfinance call to compile consensus, ownership and trading stats."""
    try:
        import yfinance as yf
        import pandas as pd
        
        ticker_obj = yf.Ticker(yf_ticker)
        info = ticker_obj.info or {}
        
        current_price = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
        )
        if current_price is None:
            return {
                "available": False,
                "reason": "Ticker not found or market data unavailable on Yahoo Finance."
            }
        
        currency = info.get("currency") or "USD"
        
        # 1. Analyst Consensus
        recommendations = ["buy", "hold", "sell"]
        rec_key = info.get("recommendationKey")
        if rec_key and rec_key.lower() in recommendations:
            rec_key = rec_key.lower()
        else:
            rec_key = None
            
        num_opinions = info.get("numberOfAnalystOpinions")
        target_mean = info.get("targetMeanPrice")
        
        analyst_available = (num_opinions is not None and num_opinions > 0) or (target_mean is not None)
        
        analyst_consensus = {
            "available": analyst_available,
            "reason": None if analyst_available else "No analyst coverage data available for this ticker",
            "recommendation_key": rec_key,
            "recommendation_mean": info.get("recommendationMean"),
            "target_mean_price": target_mean,
            "target_high_price": info.get("targetHighPrice"),
            "target_low_price": info.get("targetLowPrice"),
            "target_median_price": info.get("targetMedianPrice"),
            "number_of_analyst_opinions": num_opinions,
        }
        
        # 2. Ownership
        held_inst = info.get("heldPercentInstitutions")
        held_insider = info.get("heldPercentInsiders")
        
        inst_holders = []
        major_holders_breakdown = {}
        
        try:
            inst_df = ticker_obj.institutional_holders
            if isinstance(inst_df, pd.DataFrame) and not inst_df.empty:
                records = inst_df.to_dict(orient="records")
                for r in records[:8]:
                    date_rep = r.get("Date Reported")
                    date_rep_str = date_rep.strftime("%Y-%m-%d") if hasattr(date_rep, "strftime") else (str(date_rep) if date_rep else None)
                    pct = r.get("pctHeld")
                    if pct is not None:
                        pct = float(pct) * 100.0
                    inst_holders.append({
                        "holder": str(r.get("Holder")),
                        "shares": int(r.get("Shares")) if r.get("Shares") is not None else None,
                        "date_reported": date_rep_str,
                        "pct_out": pct,
                        "value": float(r.get("Value")) if r.get("Value") is not None else None,
                    })
        except Exception as e:
            logger.warning(f"Could not fetch institutional holders for {yf_ticker}: {e}")

        try:
            major_df = ticker_obj.major_holders
            if isinstance(major_df, pd.DataFrame) and not major_df.empty:
                raw_dict = major_df.to_dict().get("Value", {})
                major_holders_breakdown = {str(k): v for k, v in raw_dict.items()}
        except Exception as e:
            logger.warning(f"Could not fetch major holders breakdown for {yf_ticker}: {e}")

        ownership_available = (held_inst is not None or held_insider is not None or len(inst_holders) > 0)
        
        ownership = {
            "available": ownership_available,
            "reason": None if ownership_available else "No public ownership structure data available for this ticker",
            "held_percent_institutions": float(held_inst) * 100.0 if held_inst is not None else None,
            "held_percent_insiders": float(held_insider) * 100.0 if held_insider is not None else None,
            "top_institutional_holders": inst_holders,
            "major_holders_breakdown": major_holders_breakdown,
        }
        
        # 3. Trading & Momentum
        fifty_day = info.get("fiftyDayAverage")
        two_hundred_day = info.get("twoHundredDayAverage")
        beta = info.get("beta")
        
        price_vs_fifty = None
        price_vs_two_hundred = None
        if fifty_day and current_price:
            price_vs_fifty = round(((float(current_price) - float(fifty_day)) / float(fifty_day)) * 100, 2)
        if two_hundred_day and current_price:
            price_vs_two_hundred = round(((float(current_price) - float(two_hundred_day)) / float(two_hundred_day)) * 100, 2)
            
        trading_available = (fifty_day is not None or two_hundred_day is not None)
        
        trading_momentum = {
            "available": trading_available,
            "reason": None if trading_available else "No trading or momentum averages available for this ticker",
            "short_percent_of_float": float(info.get("shortPercentOfFloat")) * 100.0 if info.get("shortPercentOfFloat") is not None else None,
            "shares_short": info.get("sharesShort"),
            "short_ratio": info.get("shortRatio"),
            "fifty_day_average": fifty_day,
            "two_hundred_day_average": two_hundred_day,
            "beta": beta if beta is not None else 1.0,
            "price_vs_fifty_day_pct": price_vs_fifty,
            "price_vs_two_hundred_day_pct": price_vs_two_hundred,
        }
        
        own_metrics = {
            "ticker": yf_ticker.split(".")[0],
            "pe_ratio": info.get("trailingPE"),
            "gross_margin": info.get("grossMargins"),
            "operating_margin": info.get("operatingMargins"),
            "net_margin": info.get("profitMargins"),
            "roe": info.get("returnOnEquity"),
        }
        
        return {
            "available": True,
            "ticker": yf_ticker.split(".")[0],
            "currency": currency,
            "current_price": float(current_price) if current_price is not None else None,
            "analyst_consensus": analyst_consensus,
            "ownership": ownership,
            "trading_momentum": trading_momentum,
            "own_metrics": own_metrics,
        }
    except Exception as exc:
        logger.warning(f"Error fetching market intel sync for {yf_ticker}: {exc}")
        return {
            "available": False,
            "reason": f"Market intel error: {exc}"
        }


async def get_market_intel(ticker_symbol: str, exchange: str = "", peer_tickers_list: list[str] = []) -> dict:
    """
    Async wrapper to compile structured yfinance market statistics for target + peer tickers.
    Employs parallel fetching, Redis caching and strict asyncio timeouts.
    """
    from app.core.cache import cache
    import datetime

    yf_ticker = _resolve_ticker(ticker_symbol, exchange)
    cache_key = f"market_intel:{yf_ticker}"

    cached = await cache.get(cache_key)
    if cached is not None:
        logger.debug(f"market_intel cache HIT: {cache_key}")
        return cached

    loop = asyncio.get_event_loop()
    try:
        data = await asyncio.wait_for(
            loop.run_in_executor(None, _fetch_market_intel_sync, yf_ticker),
            timeout=25.0
        )
    except asyncio.TimeoutError:
        logger.warning(f"Market intel fetch timed out for {yf_ticker}")
        data = {
            "available": False,
            "reason": "Yahoo Finance did not respond in time"
        }

    as_of = datetime.datetime.utcnow().isoformat() + "Z"

    if not data.get("available"):
        result = {
            "ticker": ticker_symbol.upper(),
            "currency": "USD",
            "current_price": None,
            "analyst_consensus": {"available": False, "reason": data.get("reason", "Data unavailable")},
            "ownership": {"available": False, "reason": data.get("reason", "Data unavailable")},
            "trading_momentum": {"available": False, "reason": data.get("reason", "Data unavailable")},
            "peer_comparison": {"available": False, "reason": data.get("reason", "Data unavailable"), "peers": []},
            "as_of": as_of
        }
        await cache.set(cache_key, result, ttl=30)
        return result

    # Fetch peer metrics concurrently
    peer_results = []
    if peer_tickers_list:
        try:
            tasks = [
                loop.run_in_executor(None, _fetch_peer_metrics_sync, _resolve_ticker(pt, exchange))
                for pt in peer_tickers_list
            ]
            peer_results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=20.0)
        except Exception as e:
            logger.warning(f"Failed to fetch peer metrics: {e}")

    peers_list = []
    if data.get("own_metrics"):
        peers_list.append(data["own_metrics"])
    for pr in peer_results:
        if pr:
            peers_list.append(pr)

    final_result = {
        "ticker": data["ticker"],
        "currency": data["currency"],
        "current_price": data.get("current_price"),
        "analyst_consensus": data["analyst_consensus"],
        "ownership": data["ownership"],
        "trading_momentum": data["trading_momentum"],
        "peer_comparison": {
            "available": len(peers_list) > 0,
            "reason": None if len(peers_list) > 0 else "No peer comparison data available",
            "peers": peers_list
        },
        "as_of": as_of
    }

    await cache.set(cache_key, final_result, ttl=1800)
    return final_result

