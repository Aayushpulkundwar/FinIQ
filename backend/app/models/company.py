from typing import Optional
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel


class Company(BaseModel):
    """
    SQLAlchemy model representing a Company entity in the FinIQ platform.
    Inherits primary key (UUID) and timestamps (created_at, updated_at) from BaseModel.
    """
    __tablename__ = "companies"

    company_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ticker_symbol: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    exchange: Mapped[str] = mapped_column(String(100), nullable=False)
    sector: Mapped[str] = mapped_column(String(100), nullable=False)
    industry: Mapped[str] = mapped_column(String(100), nullable=False)
    isin: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    peer_tickers: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default="")
