from typing import List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.financial import FinancialStatement, FinancialPeriod, PeriodType
from app.repositories.base import BaseRepository


class FinancialRepository(BaseRepository[FinancialStatement]):
    """
    Repository handling PostgreSQL operations for Financial Intelligence data.
    Keeps database access strictly decoupled from service logic.
    """
    def __init__(self, db: AsyncSession):
        super().__init__(FinancialStatement, db)

    async def get_or_create_period(
        self,
        company_id: UUID,
        fiscal_year: int,
        period_type: PeriodType,
        currency: str,
    ) -> FinancialPeriod:
        """
        Fetches an existing FinancialPeriod or creates a new one.
        Ensures idempotent upsert for the same company/year/period combination.
        Requires explicit reporting currency — silent defaulting is disallowed.
        """
        if not currency or not str(currency).strip():
            raise ValueError("Explicit currency is required when creating a FinancialPeriod — silent defaulting is disallowed.")

        stmt = select(FinancialPeriod).where(
            FinancialPeriod.company_id == company_id,
            FinancialPeriod.fiscal_year == fiscal_year,
            FinancialPeriod.period_type == period_type
        )
        result = await self.db.execute(stmt)
        period = result.scalars().first()

        if not period:
            period = FinancialPeriod(
                company_id=company_id,
                fiscal_year=fiscal_year,
                period_type=period_type,
                currency=currency.strip().upper()
            )
            self.db.add(period)
            await self.db.flush()

        return period

    async def get_statements_by_company(
        self,
        company_id: UUID,
        limit: int = 8
    ) -> List[FinancialStatement]:
        """
        Fetches historical financial statements for a company ordered by fiscal year descending.
        Used by TrendAnalyzer for multi-period comparisons.
        """
        stmt = (
            select(FinancialStatement)
            .join(FinancialPeriod, FinancialStatement.period_id == FinancialPeriod.id)
            .where(FinancialStatement.company_id == company_id)
            .order_by(FinancialPeriod.fiscal_year.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
