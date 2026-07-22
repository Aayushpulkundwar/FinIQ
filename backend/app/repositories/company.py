from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.company import Company
from app.repositories.base import BaseRepository


class CompanyRepository(BaseRepository[Company]):
    """
    Repository for PostgreSQL database operations on the Company entity.
    Keeps database operations separated from service layer logic.
    """
    def __init__(self, db: AsyncSession):
        super().__init__(Company, db)

    async def get_by_ticker(self, ticker_symbol: str) -> Optional[Company]:
        """Fetch a company by its unique stock ticker symbol."""
        stmt = select(self.model).filter(self.model.ticker_symbol == ticker_symbol)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_by_isin(self, isin: str) -> Optional[Company]:
        """Fetch a company by its unique ISIN (International Securities Identification Number)."""
        stmt = select(self.model).filter(self.model.isin == isin)
        result = await self.db.execute(stmt)
        return result.scalars().first()
