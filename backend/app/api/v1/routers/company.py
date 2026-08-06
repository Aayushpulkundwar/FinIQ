from typing import Any, Dict, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.company import Company, CompanyCreate, CompanyUpdate
from app.schemas.news import CompanyNewsResponse
from app.schemas.yahoo_finance import FinancialSummaryResponse, RecommendationResponse
from app.services.company import CompanyService
from app.services.market_data import get_market_data, get_yfinance_dcf_inputs
from app.services.yahoo_finance_summary import get_financial_summary
from app.services.valuation import compute_dcf_intrinsic_value
from loguru import logger
from app.models.user import User
from sqlalchemy import select
from datetime import datetime

router = APIRouter()


async def get_current_user_or_default(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency helper that attempts to resolve the current authenticated user via JWT,
    falling back to the first user in the database for stateless local development environments.
    """
    try:
        from app.core.security import get_current_user
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            from fastapi.security import HTTPAuthorizationCredentials
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
            return await get_current_user(credentials=creds, db=db)
    except Exception as e:
        logger.warning(f"Optional JWT authentication failed: {e}. Falling back to default user database query.")
    
    from app.models.user import User as UserModel
    stmt = select(UserModel).limit(1)
    res = await db.execute(stmt)
    user = res.scalars().first()
    if not user:
        from app.core.security import hash_password
        from app.models.user import UserRole
        user = UserModel(
            email="default_analyst@finiq.com",
            hashed_password=hash_password("password123"),
            role=UserRole.analyst,
            is_active=True
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("Database has no users. Seeded a default analyst user.")
    return user


@router.get("/search", response_model=List[Company])
async def search_companies(
    q: str = "",
    db: AsyncSession = Depends(get_db)
) -> List[Company]:
    """
    Search companies table by ticker symbol or company name (case-insensitive, limit 10).
    """
    if not q:
        return []
    
    from app.models.company import Company as CompanyModel
    from sqlalchemy import or_

    stmt = (
        select(CompanyModel)
        .filter(
            or_(
                CompanyModel.ticker_symbol.ilike(f"%{q}%"),
                CompanyModel.company_name.ilike(f"%{q}%")
            )
        )
        .limit(10)
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.get("/recent", response_model=List[Company])
async def get_recent_companies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default)
) -> List[Company]:
    """
    Returns the current user's last 5 selected companies ordered by selected_at desc.
    """
    from app.models.recent_company_selection import RecentCompanySelection
    from app.models.company import Company as CompanyModel

    stmt = (
        select(CompanyModel)
        .join(RecentCompanySelection, RecentCompanySelection.company_id == CompanyModel.id)
        .filter(RecentCompanySelection.user_id == current_user.id)
        .order_by(RecentCompanySelection.selected_at.desc())
        .limit(5)
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.post("/{id}/select", status_code=status.HTTP_200_OK)
async def select_company(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default)
) -> dict:
    """
    Record that a user selected a company, upserting the selected_at timestamp.
    """
    service = CompanyService(db)
    try:
        await service.get_company(id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    from app.models.recent_company_selection import RecentCompanySelection

    stmt = select(RecentCompanySelection).filter(
        RecentCompanySelection.user_id == current_user.id,
        RecentCompanySelection.company_id == id
    )
    res = await db.execute(stmt)
    selection = res.scalars().first()

    if selection:
        selection.selected_at = datetime.utcnow()
    else:
        selection = RecentCompanySelection(
            user_id=current_user.id,
            company_id=id,
            selected_at=datetime.utcnow()
        )
        db.add(selection)
    
    await db.commit()
    return {"status": "success", "company_id": str(id)}


@router.get("/{id}/live-price", response_model=Dict[str, Any])
async def get_company_live_price(
    id: UUID,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Fetch real-time stock price and minimal OHLC data for a company, Redis-cached with a 5-second TTL.
    """
    from app.services.market_data import _resolve_ticker
    from app.core.cache import cache
    import asyncio
    import yfinance as yf

    service = CompanyService(db)
    try:
        company = await service.get_company(id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    yf_ticker = _resolve_ticker(company.ticker_symbol, company.exchange or "")
    cache_key = f"live_price:{yf_ticker}"

    cached = await cache.get(cache_key)
    if cached is not None:
        logger.debug(f"live_price cache HIT: {cache_key}")
        return cached

    def _fetch_live_price() -> Dict[str, Any]:
        ticker_obj = yf.Ticker(yf_ticker)
        info = ticker_obj.info or {}
        
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        if current_price is None:
            # Fallback: get last close from 1D history
            hist = ticker_obj.history(period="1d")
            if not hist.empty:
                current_price = hist["Close"].iloc[-1]
                open_val = hist["Open"].iloc[-1]
                high_val = hist["High"].iloc[-1]
                low_val = hist["Low"].iloc[-1]
                close_val = hist["Close"].iloc[-1]
                volume_val = hist["Volume"].iloc[-1]
            else:
                current_price = info.get("previousClose") or 0.0
                open_val = current_price
                high_val = current_price
                low_val = current_price
                close_val = current_price
                volume_val = 0
        else:
            open_val = info.get("open") or info.get("regularMarketOpen") or current_price
            high_val = info.get("dayHigh") or info.get("regularMarketDayHigh") or current_price
            low_val = info.get("dayLow") or info.get("regularMarketDayLow") or current_price
            close_val = current_price
            volume_val = info.get("volume") or info.get("regularMarketVolume") or 0

        sparkline_prices = []
        try:
            # Pull 1D at 1-minute interval for the sparkline (last 30 minutes)
            hist_1m = ticker_obj.history(period="1d", interval="1m")
            if not hist_1m.empty:
                last_30 = hist_1m.tail(30)
                for timestamp, row in last_30.iterrows():
                    sparkline_prices.append({
                        "time": timestamp.strftime("%H:%M"),
                        "price": round(float(row["Close"]), 2)
                    })
        except Exception as e:
            logger.warning(f"Failed to fetch sparkline data for {yf_ticker}: {e}")

        if not sparkline_prices and current_price is not None:
            sparkline_prices = [{"time": "Now", "price": round(float(current_price), 2)}]

        return {
            "ticker": yf_ticker,
            "current_price": round(float(current_price), 2) if current_price is not None else None,
            "open": round(float(open_val), 2) if open_val is not None else None,
            "high": round(float(high_val), 2) if high_val is not None else None,
            "low": round(float(low_val), 2) if low_val is not None else None,
            "close": round(float(close_val), 2) if close_val is not None else None,
            "volume": int(volume_val) if volume_val is not None else None,
            "sparkline": sparkline_prices,
            "as_of": datetime.utcnow().isoformat() + "Z"
        }

    loop = asyncio.get_event_loop()
    try:
        data = await asyncio.wait_for(
            loop.run_in_executor(None, _fetch_live_price),
            timeout=15.0
        )
        await cache.set(cache_key, data, ttl=5)
        return data
    except Exception as e:
        logger.error(f"Live price fetch failed for {yf_ticker}: {e}")
        return {
            "ticker": yf_ticker,
            "current_price": None,
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "volume": None,
            "sparkline": [],
            "as_of": datetime.utcnow().isoformat() + "Z",
            "error": str(e)
        }


@router.get("/{id}/history", response_model=List[Dict[str, Any]])
async def get_company_history(
    id: UUID,
    range: str = "1M",
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Fetch historical price data for a company per a specified timeframe range (1D, 1W, 1M, 1Y).
    Results are cached in Redis (60s TTL for 1D, 5m TTL for other ranges).
    """
    from app.services.market_data import _resolve_ticker
    from app.core.cache import cache
    import asyncio
    import yfinance as yf

    service = CompanyService(db)
    try:
        company = await service.get_company(id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    yf_ticker = _resolve_ticker(company.ticker_symbol, company.exchange or "")
    
    range_upper = range.upper()
    if range_upper not in ("1D", "1W", "1M", "1Y"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid range parameter")

    cache_key = f"history_data:{yf_ticker}:{range_upper}"
    ttl = 60 if range_upper == "1D" else 300

    cached = await cache.get(cache_key)
    if cached is not None:
        logger.debug(f"history cache HIT: {cache_key}")
        return cached

    def _fetch_history() -> List[Dict[str, Any]]:
        ticker_obj = yf.Ticker(yf_ticker)
        
        period_map = {
            "1D": ("1d", "5m"),
            "1W": ("5d", "15m"),
            "1M": ("1mo", "1d"),
            "1Y": ("1y", "1d"),
        }
        
        period, interval = period_map[range_upper]
        hist = ticker_obj.history(period=period, interval=interval)
        
        result = []
        if not hist.empty:
            for timestamp, row in hist.iterrows():
                if range_upper in ("1D", "1W"):
                    time_str = timestamp.strftime("%Y-%m-%d %H:%M")
                else:
                    time_str = timestamp.strftime("%Y-%m-%d")
                    
                result.append({
                    "date": time_str,
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row["Volume"]),
                })
        return result

    loop = asyncio.get_event_loop()
    try:
        data = await asyncio.wait_for(
            loop.run_in_executor(None, _fetch_history),
            timeout=20.0
        )
        await cache.set(cache_key, data, ttl=ttl)
        return data
    except Exception as e:
        logger.error(f"History fetch failed for {yf_ticker}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to fetch historical data: {str(e)}"
        )


@router.post("", response_model=Company, status_code=status.HTTP_201_CREATED)
async def create_company(
    company_in: CompanyCreate, db: AsyncSession = Depends(get_db)
) -> Company:
    """
    Create a new company record.
    Checks that the ticker_symbol and isin are unique.
    """
    service = CompanyService(db)
    try:
        return await service.create_company(company_in)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )


@router.get("", response_model=List[Company])
async def list_companies(
    skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
) -> List[Company]:
    """
    Retrieve a list of companies with optional pagination.
    """
    service = CompanyService(db)
    return await service.list_companies(skip=skip, limit=limit)


@router.get("/{id}", response_model=Company)
async def get_company(
    id: UUID, db: AsyncSession = Depends(get_db)
) -> Company:
    """
    Get details of a company by its UUID.
    """
    service = CompanyService(db)
    try:
        return await service.get_company(id)
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


@router.put("/{id}", response_model=Company)
async def update_company(
    id: UUID, company_in: CompanyUpdate, db: AsyncSession = Depends(get_db)
) -> Company:
    """
    Update field values of an existing company.
    Validates uniqueness constraints if the ticker or ISIN is changed.
    """
    service = CompanyService(db)
    try:
        return await service.update_company(id, company_in)
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )


@router.delete("/{id}", response_model=Company)
async def delete_company(
    id: UUID, db: AsyncSession = Depends(get_db)
) -> Company:
    """
    Delete a company record by UUID.
    """
    service = CompanyService(db)
    try:
        return await service.delete_company(id)
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


@router.get("/{id}/market-data", response_model=Dict[str, Any])
async def get_company_market_data(
    id: UUID, db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Fetch real-time market data for a company from Yahoo Finance.

    - Looks up the company's ``ticker_symbol`` and ``exchange`` from the DB.
    - Resolves the correct yfinance suffix based on the exchange
      (e.g. NASDAQ → no suffix, NSE → ``.NS``, BSE → ``.BO``).
    - Results are Redis-cached with a 90-second TTL.
    - Returns ``{"available": false, "reason": "..."}`` on any failure
      instead of raising a 500 — the dashboard degrades gracefully.
    """
    service = CompanyService(db)
    try:
        company = await service.get_company(id)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    data = await get_market_data(company.ticker_symbol, company.exchange or "")
    return data


@router.get("/{id}/financial-summary", response_model=FinancialSummaryResponse)
async def get_company_financial_summary(
    id: UUID, db: AsyncSession = Depends(get_db)
) -> FinancialSummaryResponse:
    """
    Fetch the latest annual financial summary for a company.

    Prioritizes RAG/document-extracted financials if available in the DB,
    falling back to live Yahoo Finance fetch if no document is uploaded or if the DB query is empty.
    """
    from app.services.market_data import _resolve_ticker
    from app.models.financial import FinancialPeriod, FinancialStatement, FinancialMetric, PeriodType
    from app.models.document import Document, ProcessingStatus

    from app.core.cache import cache
    summary_cache_key = f"financial_summary:overview:{id}"
    cached_summary = await cache.get(summary_cache_key)
    if cached_summary is not None:
        logger.debug(f"financial-summary cache HIT: {summary_cache_key}")
        return FinancialSummaryResponse(**cached_summary)

    service = CompanyService(db)
    try:
        company = await service.get_company(id)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    # Fetch ratio metrics directly via dedicated financial_ratios_scraper (cached 12h)
    from app.services.financial_ratios_scraper import fetch_financial_ratios, FinancialRatios
    from app.core.cache import cache

    ratios = None
    cache_key = f"ratios:{id}"
    cached_ratios = await cache.get(cache_key)
    if cached_ratios is not None:
        try:
            ratios = FinancialRatios(**cached_ratios)
        except Exception:
            ratios = None

    if ratios is None and company.ticker_symbol:
        ratios = await fetch_financial_ratios(company.ticker_symbol, company.exchange or "")
        if ratios and ratios.available:
            await cache.set(cache_key, ratios.model_dump(), ttl=43200)

    scraped_roe = ratios.roe_percent if ratios and ratios.available else None

    # ── PRIMARY PATH: Try yfinance summary FIRST ───────────────────────────
    if company.ticker_symbol:
        try:
            data = await get_financial_summary(company.ticker_symbol, company.exchange or "")
            if data and data.get("available"):
                if scraped_roe is not None:
                    data["roe"] = scraped_roe
                    data["roe_source"] = "ratio_scraper"
                resp_obj = FinancialSummaryResponse(**data)
                await cache.set(summary_cache_key, resp_obj.model_dump(), ttl=1800)
                logger.info(f"get_company_financial_summary: Served live yfinance summary for {company.ticker_symbol}")
                return resp_obj
        except Exception as yf_err:
            logger.warning(f"get_company_financial_summary: yfinance fetch failed for {company.ticker_symbol}: {yf_err}. Falling back to DB/PDF.")

    # ── FALLBACK PATH: DB / PDF Filing summary when yfinance fails ─────────
    stmt = (
        select(FinancialPeriod, FinancialStatement, FinancialMetric)
        .join(FinancialStatement, FinancialStatement.period_id == FinancialPeriod.id)
        .outerjoin(FinancialMetric, FinancialMetric.statement_id == FinancialStatement.id)
        .where(
            FinancialPeriod.company_id == id,
            FinancialPeriod.period_type == PeriodType.annual
        )
        .order_by(FinancialPeriod.fiscal_year.desc())
        .limit(1)
    )
    res = await db.execute(stmt)
    row = res.first()

    if row:
        period, statement, metric = row
        if statement.revenue is not None or statement.net_profit is not None:
            if not period.currency or str(period.currency).strip().upper() in ["", "UNKNOWN", "NULL", "NONE"]:
                logger.warning(
                    f"FinancialPeriod {period.id} for company {company.ticker_symbol} has missing or unverified currency. "
                    "Rejecting database summary to prevent displaying mislabeled currency values."
                )
                return FinancialSummaryResponse(
                    ticker=_resolve_ticker(company.ticker_symbol, company.exchange or ""),
                    available=False,
                    reason="currency_unverified",
                )

            fallback_source = "uploaded_filings_yfinance_unavailable"
            final_roe = scraped_roe if scraped_roe is not None else (float(metric.roe) if metric and metric.roe is not None else None)
            final_roe_source = "ratio_scraper" if scraped_roe is not None else fallback_source

            resp_obj = FinancialSummaryResponse(
                ticker=_resolve_ticker(company.ticker_symbol, company.exchange or ""),
                available=True,
                fiscal_year=f"FY{period.fiscal_year}",
                currency=period.currency,
                revenue=float(statement.revenue) if statement.revenue is not None else None,
                revenue_source=fallback_source,
                ebitda=float(statement.ebitda) if statement.ebitda is not None else None,
                ebitda_source=fallback_source,
                net_profit=float(statement.net_profit) if statement.net_profit is not None else None,
                net_profit_source=fallback_source,
                roe=final_roe,
                roe_source=final_roe_source,
            )
            await cache.set(summary_cache_key, resp_obj.model_dump(), ttl=1800)
            return resp_obj

    # 3. Final Fallback if yfinance failed and no DB statement exists
    data = await get_financial_summary(company.ticker_symbol, company.exchange or "")
    if scraped_roe is not None and data.get("available"):
        data["roe"] = scraped_roe
        data["roe_source"] = "ratio_scraper"
    resp_obj = FinancialSummaryResponse(**data)
    if resp_obj.available:
        await cache.set(summary_cache_key, resp_obj.model_dump(), ttl=1800)
    return resp_obj


@router.get("/{id}/recommendation", response_model=RecommendationResponse)
async def get_company_recommendation(
    id: UUID, db: AsyncSession = Depends(get_db)
) -> RecommendationResponse:
    """
    Compute a Buy / Hold / Sell recommendation for a company using a
    live DCF intrinsic-value estimate sourced entirely from Yahoo Finance.

    Flow
    ----
    1. Look up the company's ticker_symbol and exchange from the DB.
    2. Fetch live fundamentals (FCF, shares outstanding, growth) via yfinance.
    3. If any required field is missing or the fetch fails, return
       signal='Unavailable' with a reason code — never a 500.
    4. Run the pure compute_dcf_intrinsic_value() function (same logic as
       the DB-backed ValuationService) using live CAPM-derived WACC
       computed from beta, risk-free rate, and capital structure weights
       sourced from yfinance — the exact same logic as ValuationService.
    5. Compare intrinsic value vs current price:
         Buy  if upside >  15%
         Sell if upside < -15%
         Hold otherwise
    """
    service = CompanyService(db)
    try:
        company = await service.get_company(id)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    logger.bind(ticker=company.ticker_symbol, exchange=company.exchange).info(
        "GET /recommendation: fetching yfinance DCF inputs"
    )

    # Fetch live DCF inputs from Yahoo Finance
    dcf_inputs = await get_yfinance_dcf_inputs(
        company.ticker_symbol, company.exchange or ""
    )

    if not dcf_inputs.get("available"):
        reason = dcf_inputs.get("reason", "data_fetch_failed")
        logger.warning(
            f"Recommendation unavailable for {company.ticker_symbol}: "
            f"{reason} — {dcf_inputs.get('missing', '')}"
        )
        return RecommendationResponse(
            signal="Unavailable",
            reason=reason,
        )

    # ── Compute live CAPM WACC from yfinance inputs ──────────────────────
    # Mirror the exact same logic used by ValuationService so both surfaces
    # always produce an identical intrinsic share price.
    perpetuity_growth_rate = 0.02

    beta = dcf_inputs.get("beta") or 1.0
    risk_free_rate = dcf_inputs.get("risk_free_rate") or 0.040
    erp = 0.055  # equity risk premium — same EQUITY_RISK_PREMIUM_DEFAULT as ValuationService
    cost_of_equity = risk_free_rate + (beta * erp)

    tax_rate = dcf_inputs.get("tax_rate") or 0.21
    pretax_cost_of_debt = dcf_inputs.get("cost_of_debt") or 0.060
    cost_of_debt = pretax_cost_of_debt * (1 - tax_rate)

    current_price = dcf_inputs["current_price"]
    shares_outstanding = dcf_inputs["shares_outstanding"]
    debt = dcf_inputs.get("debt", 0.0)

    # Capital structure weights using market cap (preferred) exactly as ValuationService does
    if current_price > 0 and shares_outstanding > 0:
        equity_val = float(shares_outstanding) * float(current_price)
        total_cap = equity_val + float(debt)
        equity_weight = equity_val / total_cap if total_cap > 0 else 0.80
        debt_weight = float(debt) / total_cap if total_cap > 0 else 0.20
    else:
        equity_weight = 0.80
        debt_weight = 0.20

    wacc = (equity_weight * cost_of_equity) + (debt_weight * cost_of_debt)
    from app.services.valuation_utils import clamp_wacc, clamp_growth_rate
    wacc, _ = clamp_wacc(wacc)

    fcf_growth_rate = dcf_inputs["fcf_growth_rate"]
    fcf_growth_source = dcf_inputs.get("fcf_growth_source", "unknown")
    fcf_growth_rate, _ = clamp_growth_rate(fcf_growth_rate, fcf_growth_source)

    # Log raw yfinance inputs before DCF calculation
    logger.info(
        f"DCF Debug Inputs for {company.ticker_symbol}: "
        f"raw_fcf={dcf_inputs['free_cash_flow']} (raw units), "
        f"shares_outstanding={dcf_inputs['shares_outstanding']} (raw units), "
        f"growth_rate={fcf_growth_rate}, "
        f"wacc={wacc}, "
        f"perpetuity_growth_rate={perpetuity_growth_rate}, "
        f"cash={dcf_inputs['cash']}, "
        f"debt={dcf_inputs['debt']}"
    )

    try:
        (
            intrinsic_share_price,
            projected_fcfs,
            terminal_value,
            enterprise_value,
            equity_value,
        ) = compute_dcf_intrinsic_value(
            baseline_fcf=dcf_inputs["free_cash_flow"],
            fcf_growth_rate=fcf_growth_rate,
            wacc=wacc,
            shares_outstanding=dcf_inputs["shares_outstanding"],
            perpetuity_growth_rate=perpetuity_growth_rate,
            cash=dcf_inputs["cash"],
            debt=dcf_inputs["debt"],
        )
        
        # Calculate PV of forecast flows and PV of terminal value for logging
        pv_of_fcfs_log = sum(fcf / ((1 + wacc) ** (idx + 1)) for idx, fcf in enumerate(projected_fcfs))
        pv_of_tv_log = terminal_value / ((1 + wacc) ** len(projected_fcfs))

        # Log intermediate DCF values before discounting/division
        logger.info(
            f"DCF Debug Projections for {company.ticker_symbol}:\n"
            f"  Current FCF/UFCF: {dcf_inputs['free_cash_flow']}\n"
            f"  Growth Rate: {dcf_inputs['fcf_growth_rate']}\n"
            f"  WACC: {wacc}\n"
            f"  Terminal Growth: {perpetuity_growth_rate}\n"
            f"  Projected FCFs: {projected_fcfs}\n"
            f"  PV of Forecast Cash Flows: {pv_of_fcfs_log}\n"
            f"  Terminal Value: {terminal_value}\n"
            f"  PV of Terminal Value: {pv_of_tv_log}\n"
            f"  Enterprise Value: {enterprise_value}\n"
            f"  Cash: {dcf_inputs['cash']}\n"
            f"  Debt: {dcf_inputs['debt']}\n"
            f"  Equity Value: {equity_value}\n"
            f"  Shares Outstanding: {dcf_inputs['shares_outstanding']}\n"
            f"  Intrinsic Value Per Share: {intrinsic_share_price}"
        )
    except Exception as exc:
        logger.error(f"DCF computation failed for {company.ticker_symbol}: {exc}")
        return RecommendationResponse(
            signal="Unavailable",
            reason="data_fetch_failed",
        )

    current_price = dcf_inputs["current_price"]
    if current_price <= 0:
        return RecommendationResponse(
            signal="Unavailable",
            reason="insufficient_data",
        )

    upside_pct = round(((intrinsic_share_price - current_price) / current_price) * 100, 2)

    # ── Post-Valuation Sanity Checks ──
    sanity_failed_reason = None
    
    # 1. Implied P/E check
    net_profit = dcf_inputs.get("net_profit")
    shares = dcf_inputs.get("shares_outstanding")
    if net_profit and shares and shares > 0 and net_profit > 0:
        eps = net_profit / shares
        implied_pe = intrinsic_share_price / eps
        if implied_pe < 1.0 or implied_pe > 120.0:
            sanity_failed_reason = f"Implied P/E ({implied_pe:.1f}x) is outside plausible sanity range (1.0x to 120.0x)"
    
    # 2. Implied EV/EBITDA check
    ebitda = dcf_inputs.get("ebitda")
    if ebitda and ebitda > 0:
        implied_ev_ebitda = enterprise_value / ebitda
        if implied_ev_ebitda < 1.0 or implied_ev_ebitda > 60.0:
            sanity_failed_reason = f"Implied EV/EBITDA ({implied_ev_ebitda:.1f}x) is outside plausible sanity range (1.0x to 60.0x)"

    # 3. Market Price Deviation check
    deviation_pct = (intrinsic_share_price - current_price) / current_price
    if deviation_pct > 1.50 or deviation_pct < -0.90:
        sanity_failed_reason = f"Intrinsic value deviation ({deviation_pct:+.1%}) exceeds plausible bounds (+150% / -90%)"

    if sanity_failed_reason:
        logger.warning(
            f"DCF valuation for {company.ticker_symbol} failed sanity checks: {sanity_failed_reason}. "
            f"Intrinsic={intrinsic_share_price}, Price={current_price}, EV={enterprise_value}"
        )
        return RecommendationResponse(
            signal="Unavailable",
            current_price=current_price,
            intrinsic_value=intrinsic_share_price,
            upside_pct=upside_pct,
            currency=dcf_inputs.get("currency"),
            reason="failed_sanity_checks",
            wacc=round(wacc, 4),
            terminal_growth_rate=perpetuity_growth_rate,
        )

    # Cross-check intrinsic value vs market price (flag if deviation > 80%)
    deviation = abs(intrinsic_share_price - current_price) / current_price
    if deviation > 0.80:
        logger.warning(
            f"DCF intrinsic value deviation exceeds 80% for {company.ticker_symbol}: "
            f"Price={current_price}, Intrinsic={intrinsic_share_price}, Deviation={deviation:.2%}. "
            f"Flagging valuation for review."
        )
        return RecommendationResponse(
            signal="Unavailable",
            current_price=current_price,
            intrinsic_value=intrinsic_share_price,
            upside_pct=upside_pct,
            currency=dcf_inputs.get("currency"),
            reason="valuation_under_review",
            wacc=round(wacc, 4),
            terminal_growth_rate=perpetuity_growth_rate,
        )

    if upside_pct > 15:
        signal = "Buy"
    elif upside_pct < -15:
        signal = "Sell"
    else:
        signal = "Hold"

    logger.bind(
        ticker=company.ticker_symbol,
        current_price=current_price,
        intrinsic_value=intrinsic_share_price,
        upside_pct=upside_pct,
        signal=signal,
    ).info("Recommendation computed successfully.")

    return RecommendationResponse(
        signal=signal,
        current_price=current_price,
        intrinsic_value=intrinsic_share_price,
        upside_pct=upside_pct,
        currency=dcf_inputs.get("currency"),
        wacc=round(wacc, 4),
        terminal_growth_rate=perpetuity_growth_rate,
    )


# ───────────────────────────────────────────────────────────────────────────
# Live Financials tab API
# ───────────────────────────────────────────────────────────────────────────

financials_router = APIRouter()


def _fetch_detailed_financials_sync(yf_ticker: str) -> Dict[str, Any]:
    import yfinance as yf
    import math
    from datetime import datetime, timezone
    from app.services.yahoo_finance_summary import _get_row, _first_value, _safe_float

    # yfinance >= 1.5.1 uses curl_cffi Chrome impersonation by default;
    # do NOT pass session= as it breaks financial-statement fetches.
    ticker_obj = yf.Ticker(yf_ticker)

    # Pull DataFrames
    try:
        inc = ticker_obj.income_stmt
    except Exception:
        inc = None

    try:
        q_inc = ticker_obj.quarterly_income_stmt
    except Exception:
        q_inc = None

    try:
        bal = ticker_obj.balance_sheet
    except Exception:
        bal = None

    try:
        info = ticker_obj.info or {}
    except Exception:
        info = {}

    if inc is None or inc.empty:
        raise ValueError(f"No income statement data available for {yf_ticker}")

    currency = info.get("currency") or info.get("financialCurrency") or "USD"
    fiscal_year_end = info.get("nextFiscalYearEnd") or info.get("lastFiscalYearEnd")
    if isinstance(fiscal_year_end, (int, float)):
        fiscal_year_end = datetime.fromtimestamp(fiscal_year_end, timezone.utc).isoformat()
    elif fiscal_year_end:
        fiscal_year_end = str(fiscal_year_end)

    def clean_val(v) -> Any:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def extract_periods(df, is_annual: bool) -> list:
        if df is None or df.empty:
            return []

        row_revenue = _get_row(df, "total revenue", "totalrevenue")
        row_gross_profit = _get_row(df, "gross profit", "grossprofit")
        row_operating_income = _get_row(df, "operating income", "ebit")
        row_ebitda = _get_row(df, "ebitda")
        row_net_income = _get_row(df, "net income", "netincome")
        row_eps_basic = _get_row(df, "basic eps", "basiceps")
        row_eps_diluted = _get_row(df, "diluted eps", "dilutedeps")

        periods = []
        cols = list(df.columns)
        for col in cols:
            try:
                date_str = col.strftime("%Y-%m-%d")
            except AttributeError:
                date_str = str(col)

            if is_annual:
                try:
                    period_label = f"FY{col.year}"
                except AttributeError:
                    period_label = str(col)[:4]
            else:
                try:
                    period_label = f"Q{((col.month - 1) // 3) + 1} {col.year}"
                except AttributeError:
                    period_label = date_str

            rev = clean_val(row_revenue[col]) if row_revenue is not None and col in row_revenue else None
            gp = clean_val(row_gross_profit[col]) if row_gross_profit is not None and col in row_gross_profit else None
            opinc = clean_val(row_operating_income[col]) if row_operating_income is not None and col in row_operating_income else None
            eb = clean_val(row_ebitda[col]) if row_ebitda is not None and col in row_ebitda else None
            ni = clean_val(row_net_income[col]) if row_net_income is not None and col in row_net_income else None
            eps_b = clean_val(row_eps_basic[col]) if row_eps_basic is not None and col in row_eps_basic else None
            eps_d = clean_val(row_eps_diluted[col]) if row_eps_diluted is not None and col in row_eps_diluted else None

            # EBITDA fallback calculation if ebitda is None:
            if eb is None and opinc is not None:
                row_dep = _get_row(df, "depreciation", "reconciled depreciation", "d&a")
                dep_val = clean_val(row_dep[col]) if row_dep is not None and col in row_dep else None
                if dep_val is not None:
                    eb = opinc + dep_val

            periods.append({
                "period": period_label,
                "date": date_str,
                "revenue": rev,
                "gross_profit": gp,
                "operating_income": opinc,
                "ebitda": eb,
                "net_income": ni,
                "eps_basic": eps_b,
                "eps_diluted": eps_d,
                "revenue_yoy_pct": None,
                "ebitda_yoy_pct": None,
                "net_income_yoy_pct": None
            })

        for i in range(len(periods) - 1):
            curr = periods[i]
            prev = periods[i + 1]

            if curr["revenue"] is not None and prev["revenue"] is not None and prev["revenue"] != 0:
                curr["revenue_yoy_pct"] = ((curr["revenue"] - prev["revenue"]) / abs(prev["revenue"])) * 100.0
            
            if curr["ebitda"] is not None and prev["ebitda"] is not None and prev["ebitda"] != 0:
                curr["ebitda_yoy_pct"] = ((curr["ebitda"] - prev["ebitda"]) / abs(prev["ebitda"])) * 100.0

            if curr["net_income"] is not None and prev["net_income"] is not None and prev["net_income"] != 0:
                curr["net_income_yoy_pct"] = ((curr["net_income"] - prev["net_income"]) / abs(prev["net_income"])) * 100.0

        return periods

    annual_periods = extract_periods(inc, is_annual=True)
    quarterly_periods = extract_periods(q_inc, is_annual=False)

    from app.services.financial_ratios_scraper import _to_percent
    roe_pct = _to_percent(info.get("returnOnEquity"))
    roa_pct = _to_percent(info.get("returnOnAssets"))
    gross_margin_pct = _to_percent(info.get("grossMargins"))
    operating_margin_pct = _to_percent(info.get("operatingMargins"))
    net_margin_pct = _to_percent(info.get("profitMargins"))
    debt_to_equity = clean_val(info.get("debtToEquity"))

    if debt_to_equity is None and bal is not None and not bal.empty:
        tot_debt_row = _get_row(bal, "total debt", "total debt and capital lease obligation", "totaldebt")
        equity_row = _get_row(bal, "stockholders equity", "total stockholders equity", "shareholders equity")
        tot_debt = _first_value(tot_debt_row)
        equity = _first_value(equity_row)
        if tot_debt is not None and equity is not None and equity != 0:
            debt_to_equity = (tot_debt / equity) * 100.0

    return {
        "ticker": yf_ticker,
        "currency": currency,
        "fiscal_year_end": fiscal_year_end,
        "annual": annual_periods,
        "quarterly": quarterly_periods[:8],
        "ratios": {
            "roe_pct": roe_pct,
            "roa_pct": roa_pct,
            "gross_margin_pct": gross_margin_pct,
            "operating_margin_pct": operating_margin_pct,
            "net_margin_pct": net_margin_pct,
            "debt_to_equity": debt_to_equity
        },
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "") + "Z"
    }


@financials_router.get("/api/company/{ticker}/financials", response_model=Dict[str, Any])
async def get_company_detailed_financials(
    ticker: str,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Fetch raw and comprehensive financial statements (annual + quarterly) and ratios
    for a company using yfinance. Results are cached in Redis for 15-30 minutes.
    """
    from app.services.company import CompanyService
    from app.services.market_data import _resolve_ticker
    from app.core.cache import cache
    import asyncio

    db_company = None
    try:
        service = CompanyService(db)
        db_company = await service.repository.get_by_ticker(ticker)
        if not db_company and "." in ticker:
            base_ticker = ticker.split(".")[0]
            db_company = await service.repository.get_by_ticker(base_ticker)
    except Exception as e:
        logger.warning(f"Error querying company by ticker '{ticker}': {e}")

    if db_company:
        yf_ticker = _resolve_ticker(db_company.ticker_symbol, db_company.exchange or "")
    else:
        yf_ticker = ticker

    cache_key = f"detailed_financials:v2:{yf_ticker}"
    TTL_SUCCESS = 1800  # 30 minutes
    TTL_FAILURE = 60    # 1 minute

    cached = await cache.get(cache_key)
    if cached is not None:
        if not cached.get("available", True):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "financial_data_unavailable", "ticker": ticker, "reason": cached.get("reason")}
            )
        return cached

    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, _fetch_detailed_financials_sync, yf_ticker)
        data["available"] = True
        await cache.set(cache_key, data, ttl=TTL_SUCCESS)
        return data
    except Exception as exc:
        err_msg = str(exc)
        logger.error(f"Failed to fetch detailed financials for {yf_ticker}: {exc}")
        fail_payload = {"available": False, "reason": err_msg}
        await cache.set(cache_key, fail_payload, ttl=TTL_FAILURE)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "financial_data_unavailable", "ticker": ticker, "reason": err_msg}
        )


@router.get("/{company_id}/news", response_model=CompanyNewsResponse)
async def get_company_news_endpoint(
    company_id: UUID,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
) -> CompanyNewsResponse:
    """
    Fetch real-time company news via harmonized APITube / RSS feeds, cached in Redis.
    """
    from app.services.company import CompanyService
    from app.services.unified_news import fetch_harmonized_company_news
    from app.schemas.news import CompanyNewsResponse
    from app.core.cache import cache

    company_service = CompanyService(db)
    company = await company_service.get_company(company_id)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID {company_id} not found."
        )

    cache_key = f"news:{company_id}"
    cached = await cache.get(cache_key)
    if cached is not None:
        logger.info(f"CompanyNews: CACHE HIT for company_id={company_id}")
        return CompanyNewsResponse(**cached)

    articles = await fetch_harmonized_company_news(
        company_name=company.company_name,
        ticker=company.ticker_symbol,
        limit=limit,
    )

    response_data = CompanyNewsResponse(
        company_id=company.id,
        company_name=company.company_name,
        ticker_symbol=company.ticker_symbol,
        articles=articles,
    )

    # Use 900s (15 min) for non-empty results, or 60s TTL for empty results to allow fast retry on transient failures
    ttl = 900 if len(articles) > 0 else 60
    await cache.set(cache_key, response_data.model_dump(), ttl=ttl)
    return response_data


