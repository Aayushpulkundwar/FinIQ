"""
Market Intelligence & Live Top Movers Router
=============================================
Provides live market ticker endpoints including top NSE movers.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, status
from loguru import logger
import yfinance as yf

from app.core.cache import cache
from app.core.nifty50 import NIFTY_50_TICKERS

router = APIRouter()


def _get_ist_now() -> datetime:
    """Return current timestamp in Indian Standard Time (IST, UTC+5:30)."""
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist_tz)


def _check_market_open(dt: datetime) -> bool:
    """
    NSE Market Hours: Monday to Friday, 09:15 IST to 15:30 IST.
    """
    if dt.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
    time_min = dt.hour * 60 + dt.minute
    return 555 <= time_min <= 930  # 09:15 = 555m, 15:30 = 930m


def _fetch_top_movers_sync() -> List[Dict[str, Any]]:
    """
    Synchronous batch fetch of Nifty 50 tickers via yfinance yf.download.
    Runs in a background thread executor to prevent blocking FastAPI event loop.
    """
    ticker_str = " ".join(NIFTY_50_TICKERS)
    logger.info(f"Downloading batch market data for {len(NIFTY_50_TICKERS)} NSE tickers...")
    
    df = yf.download(
        tickers=ticker_str,
        period="5d",
        group_by="ticker",
        threads=True,
        progress=False,
    )

    if df is None or df.empty:
        raise ValueError("yfinance returned an empty dataset for Nifty 50 batch download.")

    movers: List[Dict[str, Any]] = []

    for t in NIFTY_50_TICKERS:
        try:
            # Handle MultiIndex columns when group_by='ticker'
            t_data = df[t] if t in df.columns.levels[0] else None
            if t_data is not None and "Close" in t_data:
                sub_df = t_data.dropna(subset=["Close"])
                if len(sub_df) >= 2:
                    last_price = float(sub_df["Close"].iloc[-1])
                    prev_close = float(sub_df["Close"].iloc[-2])
                    if prev_close > 0:
                        chg = last_price - prev_close
                        pct = (chg / prev_close) * 100
                        clean_symbol = t.replace(".NS", "")
                        movers.append({
                            "symbol": clean_symbol,
                            "price": round(last_price, 2),
                            "change": round(chg, 2),
                            "pct_change": round(pct, 2),
                        })
        except Exception as exc:
            logger.warning(f"Failed to parse ticker {t} from batch download: {exc}")

    if not movers:
        raise ValueError("Failed to extract valid price data for any Nifty 50 ticker.")

    # Sort by highest absolute percentage change
    movers.sort(key=lambda x: abs(x["pct_change"]), reverse=True)
    return movers[:15]


@router.get("/top-movers", response_model=Dict[str, Any])
async def get_top_movers() -> Dict[str, Any]:
    """
    Fetch the top 15 price movers across Nifty 50 NSE tickers.
    Results are Redis-cached with a 60-second TTL (key: market:top_movers:v1).
    """
    cache_key = "market:top_movers:v1"
    cache_ttl = 60  # seconds

    now_ist = _get_ist_now()
    is_open = _check_market_open(now_ist)

    # 1. Try serving from Redis cache
    try:
        cached = await cache.get(cache_key)
        if cached is not None:
            logger.debug(f"top-movers cache HIT: {cache_key}")
            # Update market_open state dynamically in cached response
            cached["market_open"] = is_open
            return cached
    except Exception as err:
        logger.warning(f"Redis lookup failed for top-movers: {err}")

    # 2. Fetch fresh batch data from yfinance
    try:
        top15_movers = await asyncio.to_thread(_fetch_top_movers_sync)
        
        payload: Dict[str, Any] = {
            "as_of": now_ist.isoformat(),
            "market_open": is_open,
            "movers": top15_movers,
        }

        # Cache in Redis
        try:
            await cache.set(cache_key, payload, ttl=cache_ttl)
        except Exception as cerr:
            logger.warning(f"Failed to write top-movers to Redis: {cerr}")

        return payload

    except Exception as exc:
        logger.error(f"yfinance batch download failed: {exc}")

        # Fallback to stale Redis cache if available
        try:
            stale = await cache.get(cache_key)
            if stale is not None:
                logger.info("Serving stale Redis cache for top-movers after yfinance error.")
                stale["market_open"] = is_open
                return stale
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Live NSE market movers currently unavailable. Please try again shortly.",
        )
