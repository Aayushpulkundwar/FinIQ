import uuid
from sqlalchemy import String, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseModel


class Portfolio(BaseModel):
    """
    SQLAlchemy model representing a user portfolio.
    """
    __tablename__ = "portfolios"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Relationships
    holdings = relationship("PortfolioHolding", back_populates="portfolio", cascade="all, delete-orphan")


class PortfolioHolding(BaseModel):
    """
    SQLAlchemy model representing a specific stock holding inside a user portfolio.
    """
    __tablename__ = "portfolio_holdings"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shares: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    average_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Relationships
    portfolio = relationship("Portfolio", back_populates="holdings")
    company = relationship("Company")


class Watchlist(BaseModel):
    """
    SQLAlchemy model representing a user watchlist.
    """
    __tablename__ = "watchlists"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Relationships
    items = relationship("WatchlistItem", back_populates="watchlist", cascade="all, delete-orphan")


class WatchlistItem(BaseModel):
    """
    SQLAlchemy model representing a company item inside a watchlist.
    """
    __tablename__ = "watchlist_items"

    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Relationships
    watchlist = relationship("Watchlist", back_populates="items")
    company = relationship("Company")
