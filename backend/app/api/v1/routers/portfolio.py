import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import get_current_user, RateLimiter
from app.models.user import User
from app.repositories.portfolio import PortfolioRepository
from app.services.portfolio_intelligence import PortfolioIntelligenceService
from app.schemas.portfolio import (
    PortfolioCreate, PortfolioOut, HoldingCreate, PortfolioAnalysisResponse,
    PortfolioRecommendationResponse, WatchlistCreate, WatchlistOut, WatchlistAddCompany
)


router = APIRouter()


# ── Portfolio API Endpoints ───────────────────────────────────────────────────

@router.post(
    "",
    response_model=PortfolioOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RateLimiter(calls=10, period=60))]
)
async def create_portfolio(
    payload: PortfolioCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> PortfolioOut:
    """Create a new investment portfolio for the active user."""
    repo = PortfolioRepository(db)
    portfolio = await repo.create_portfolio(name=payload.name, user_id=current_user.id)
    await db.commit()

    # Log security audit trail
    await repo.log_audit(
        action="portfolio_create",
        details=f"Portfolio name: {portfolio.name}",
        user_id=current_user.id
    )
    await db.commit()

    service = PortfolioIntelligenceService(db)
    val = await service.get_portfolio_valuation(portfolio.id)
    if not val:
        raise HTTPException(status_code=404, detail="Portfolio not found after creation")
    return val


@router.get(
    "/{portfolio_id}",
    response_model=PortfolioOut,
    dependencies=[Depends(RateLimiter(calls=50, period=60))]
)
async def get_portfolio(
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> PortfolioOut:
    """Fetch user portfolio details with comprehensive calculations of returns."""
    service = PortfolioIntelligenceService(db)
    val = await service.get_portfolio_valuation(portfolio_id)
    if not val:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # Assert ownership
    if val.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this portfolio")

    return val


@router.post(
    "/{portfolio_id}/holdings",
    response_model=PortfolioOut,
    dependencies=[Depends(RateLimiter(calls=20, period=60))]
)
async def add_holding(
    portfolio_id: uuid.UUID,
    holding: HoldingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> PortfolioOut:
    """Add or increment stock shares within an existing portfolio."""
    repo = PortfolioRepository(db)
    portfolio = await repo.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # Assert ownership
    if portfolio.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to edit this portfolio")

    await repo.add_holding(
        portfolio_id=portfolio_id,
        company_id=holding.company_id,
        shares=holding.shares,
        average_cost=holding.average_cost
    )
    await db.commit()

    # Log security audit trail
    await repo.log_audit(
        action="portfolio_add_holding",
        details=f"Company ID: {holding.company_id}, Shares: {holding.shares}, Cost: {holding.average_cost}",
        user_id=current_user.id
    )
    await db.commit()

    service = PortfolioIntelligenceService(db)
    val = await service.get_portfolio_valuation(portfolio_id)
    if not val:
         raise HTTPException(status_code=404, detail="Error retrieving updated portfolio details")
    return val


@router.get(
    "/{portfolio_id}/analysis",
    response_model=PortfolioAnalysisResponse,
    dependencies=[Depends(RateLimiter(calls=30, period=60))]
)
async def analyze_portfolio(
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> PortfolioAnalysisResponse:
    """Run diversification, sector weights, and weighted risk-score valuations."""
    service = PortfolioIntelligenceService(db)
    analysis = await service.analyze_portfolio(portfolio_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # Assert ownership
    portfolio = await service.repo.get_portfolio(portfolio_id)
    if portfolio and portfolio.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this portfolio analysis")

    return analysis


@router.get(
    "/{portfolio_id}/recommendations",
    response_model=PortfolioRecommendationResponse,
    dependencies=[Depends(RateLimiter(calls=15, period=60))]
)
async def get_portfolio_recommendations(
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> PortfolioRecommendationResponse:
    """Generate structured rebalancing recommendations using generative RAG context models."""
    service = PortfolioIntelligenceService(db)
    recs = await service.get_portfolio_recommendations(portfolio_id)
    if not recs:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # Assert ownership
    portfolio = await service.repo.get_portfolio(portfolio_id)
    if portfolio and portfolio.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to retrieve portfolio recommendations")

    return recs


# ── Watchlist API Endpoints ───────────────────────────────────────────────────

@router.post(
    "/watchlists",
    response_model=WatchlistOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RateLimiter(calls=15, period=60))]
)
async def create_watchlist(
    payload: WatchlistCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> WatchlistOut:
    """Create a new corporate monitoring watchlist."""
    repo = PortfolioRepository(db)
    watchlist = await repo.create_watchlist(name=payload.name, user_id=current_user.id)
    await db.commit()

    # Retrieve full structure
    full_watchlist = await repo.get_watchlist(watchlist.id)
    if not full_watchlist:
        raise HTTPException(status_code=404, detail="Error fetching watchlist after creation")
    
    # Map to schema manually due to nested company properties
    items_out = []
    for item in full_watchlist.items:
        items_out.append({
            "id": item.id,
            "company_id": item.company_id,
            "company_name": item.company.company_name,
            "ticker_symbol": item.company.ticker_symbol
        })

    return WatchlistOut(
        id=full_watchlist.id,
        name=full_watchlist.name,
        user_id=full_watchlist.user_id,
        items=items_out,
        created_at=full_watchlist.created_at
    )


@router.get(
    "/watchlists/{watchlist_id}",
    response_model=WatchlistOut,
    dependencies=[Depends(RateLimiter(calls=50, period=60))]
)
async def get_watchlist(
    watchlist_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> WatchlistOut:
    """Fetch watchlist detail and associated tickers."""
    repo = PortfolioRepository(db)
    watchlist = await repo.get_watchlist(watchlist_id)
    if not watchlist:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    # Assert ownership
    if watchlist.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this watchlist")

    items_out = []
    for item in watchlist.items:
        items_out.append({
            "id": item.id,
            "company_id": item.company_id,
            "company_name": item.company.company_name if item.company else "Unknown",
            "ticker_symbol": item.company.ticker_symbol if item.company else "UNK"
        })

    return WatchlistOut(
        id=watchlist.id,
        name=watchlist.name,
        user_id=watchlist.user_id,
        items=items_out,
        created_at=watchlist.created_at
    )


@router.post(
    "/watchlists/{watchlist_id}/companies",
    response_model=WatchlistOut,
    dependencies=[Depends(RateLimiter(calls=20, period=60))]
)
async def add_to_watchlist(
    watchlist_id: uuid.UUID,
    payload: WatchlistAddCompany,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> WatchlistOut:
    """Add a corporate entity ticker to an existing watchlist."""
    repo = PortfolioRepository(db)
    watchlist = await repo.get_watchlist(watchlist_id)
    if not watchlist:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    # Assert ownership
    if watchlist.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to edit this watchlist")

    await repo.add_to_watchlist(watchlist_id=watchlist_id, company_id=payload.company_id)
    await db.commit()

    # Re-fetch updated watchlist
    updated = await repo.get_watchlist(watchlist_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Error fetching updated watchlist")

    items_out = []
    for item in updated.items:
        items_out.append({
            "id": item.id,
            "company_id": item.company_id,
            "company_name": item.company.company_name if item.company else "Unknown",
            "ticker_symbol": item.company.ticker_symbol if item.company else "UNK"
        })

    return WatchlistOut(
        id=updated.id,
        name=updated.name,
        user_id=updated.user_id,
        items=items_out,
        created_at=updated.created_at
    )
