import uuid
from typing import Optional, List
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.models.portfolio import Portfolio, PortfolioHolding, Watchlist, WatchlistItem
from app.models.audit import AuditLog


class PortfolioRepository:
    """
    Repository layer for User, Portfolio, Holdings, Watchlist, and Audit log operations.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── User CRUD ─────────────────────────────────────────────────────────────

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Fetch user by email."""
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_user(self, user_id: uuid.UUID) -> Optional[User]:
        """Fetch user by primary key."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create_user(self, data: dict) -> User:
        """Create a new platform user."""
        user = User(**data)
        self.db.add(user)
        await self.db.flush()
        return user

    # ── Portfolio CRUD ────────────────────────────────────────────────────────

    async def create_portfolio(self, name: str, user_id: uuid.UUID) -> Portfolio:
        """Create a new portfolio for a user."""
        portfolio = Portfolio(name=name, user_id=user_id)
        self.db.add(portfolio)
        await self.db.flush()
        return portfolio

    async def get_portfolio(self, portfolio_id: uuid.UUID) -> Optional[Portfolio]:
        """Fetch a portfolio by ID, including its holdings."""
        stmt = (
            select(Portfolio)
            .where(Portfolio.id == portfolio_id)
            .options(selectinload(Portfolio.holdings).selectinload(PortfolioHolding.company))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_portfolios(self, user_id: uuid.UUID) -> List[Portfolio]:
        """List all portfolios owned by a user."""
        stmt = (
            select(Portfolio)
            .where(Portfolio.user_id == user_id)
            .options(selectinload(Portfolio.holdings).selectinload(PortfolioHolding.company))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ── Holding CRUD ──────────────────────────────────────────────────────────

    async def add_holding(
        self, portfolio_id: uuid.UUID, company_id: uuid.UUID, shares: float, average_cost: float
    ) -> PortfolioHolding:
        """Add or update holdings for a company within a portfolio."""
        stmt = select(PortfolioHolding).where(
            PortfolioHolding.portfolio_id == portfolio_id,
            PortfolioHolding.company_id == company_id
        )
        result = await self.db.execute(stmt)
        holding = result.scalar_one_or_none()

        if holding:
            # Re-calculate average cost basis and add shares
            total_cost = (holding.shares * holding.average_cost) + (shares * average_cost)
            holding.shares += shares
            if holding.shares > 0:
                holding.average_cost = total_cost / holding.shares
        else:
            holding = PortfolioHolding(
                portfolio_id=portfolio_id,
                company_id=company_id,
                shares=shares,
                average_cost=average_cost
            )
            self.db.add(holding)

        await self.db.flush()
        return holding

    # ── Watchlist CRUD ────────────────────────────────────────────────────────

    async def create_watchlist(self, name: str, user_id: uuid.UUID) -> Watchlist:
        """Create a new watchlist."""
        watchlist = Watchlist(name=name, user_id=user_id)
        self.db.add(watchlist)
        await self.db.flush()
        return watchlist

    async def get_watchlist(self, watchlist_id: uuid.UUID) -> Optional[Watchlist]:
        """Fetch a watchlist, including item companies."""
        stmt = (
            select(Watchlist)
            .where(Watchlist.id == watchlist_id)
            .options(selectinload(Watchlist.items).selectinload(WatchlistItem.company))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_watchlists(self, user_id: uuid.UUID) -> List[Watchlist]:
        """Retrieve all watchlists for a user."""
        stmt = (
            select(Watchlist)
            .where(Watchlist.user_id == user_id)
            .options(selectinload(Watchlist.items).selectinload(WatchlistItem.company))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def add_to_watchlist(self, watchlist_id: uuid.UUID, company_id: uuid.UUID) -> WatchlistItem:
        """Add a company to a watchlist if not already added."""
        stmt = select(WatchlistItem).where(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.company_id == company_id
        )
        result = await self.db.execute(stmt)
        item = result.scalar_one_or_none()

        if not item:
            item = WatchlistItem(watchlist_id=watchlist_id, company_id=company_id)
            self.db.add(item)
            await self.db.flush()
        return item

    # ── Audit Logging CRUD ────────────────────────────────────────────────────

    async def log_audit(self, action: str, details: Optional[str] = None, user_id: Optional[uuid.UUID] = None, ip_address: Optional[str] = None) -> AuditLog:
        """Write a structured security or user action audit log entry."""
        log = AuditLog(
            user_id=user_id,
            action=action,
            details=details,
            ip_address=ip_address
        )
        self.db.add(log)
        await self.db.flush()
        return log
