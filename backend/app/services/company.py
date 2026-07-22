from typing import List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.company import Company
from app.repositories.company import CompanyRepository
from app.schemas.company import CompanyCreate, CompanyUpdate
from app.services.base import BaseService


class CompanyService(BaseService[CompanyRepository]):
    """
    Service class orchestrating business logic for the Company entity.
    Maintains decoupling between API routes and database access patterns.
    """
    def __init__(self, db: AsyncSession):
        super().__init__(CompanyRepository(db))

    async def create_company(self, obj_in: CompanyCreate) -> Company:
        """Create a new company, validating that ticker symbol and ISIN are unique."""
        # 1. Validate ticker unique constraint
        existing_ticker = await self.repository.get_by_ticker(obj_in.ticker_symbol)
        if existing_ticker:
            raise ValueError(f"Company with ticker symbol '{obj_in.ticker_symbol}' already exists.")

        # 2. Validate ISIN unique constraint
        existing_isin = await self.repository.get_by_isin(obj_in.isin)
        if existing_isin:
            raise ValueError(f"Company with ISIN '{obj_in.isin}' already exists.")

        return await self.repository.create(obj_in=obj_in)

    async def get_company(self, id: UUID) -> Company:
        """Fetch a single company by UUID, utilizing caching."""
        from app.core.cache import cache
        from datetime import datetime
        
        cache_key = f"company:id:{id}"
        cached = await cache.get(cache_key)
        if cached:
            return Company(
                id=UUID(cached["id"]),
                company_name=cached["company_name"],
                ticker_symbol=cached["ticker_symbol"],
                exchange=cached["exchange"],
                sector=cached["sector"],
                industry=cached["industry"],
                isin=cached["isin"],
                website=cached.get("website"),
                created_at=datetime.fromisoformat(cached["created_at"]) if cached.get("created_at") else None,
                updated_at=datetime.fromisoformat(cached["updated_at"]) if cached.get("updated_at") else None,
            )

        company = await self.repository.get(id=id)
        if not company:
            raise KeyError(f"Company with ID '{id}' not found.")
        
        # Cache the record as a dict
        company_dict = {
            "id": str(company.id),
            "company_name": company.company_name,
            "ticker_symbol": company.ticker_symbol,
            "exchange": company.exchange,
            "sector": company.sector,
            "industry": company.industry,
            "isin": company.isin,
            "website": company.website,
            "created_at": company.created_at.isoformat() if company.created_at else None,
            "updated_at": company.updated_at.isoformat() if company.updated_at else None,
        }
        await cache.set(cache_key, company_dict, ttl=86400) # 24h
        return company

    async def list_companies(self, skip: int = 0, limit: int = 100) -> List[Company]:
        """Fetch multiple companies with pagination parameters."""
        return await self.repository.get_multi(skip=skip, limit=limit)

    async def update_company(self, id: UUID, obj_in: CompanyUpdate) -> Company:
        """Update a company, enforcing uniqueness and invalidating cache."""
        from app.core.cache import cache
        company = await self.get_company(id)

        # Validate ticker constraint if ticker is changed
        if obj_in.ticker_symbol and obj_in.ticker_symbol != company.ticker_symbol:
            existing = await self.repository.get_by_ticker(obj_in.ticker_symbol)
            if existing:
                raise ValueError(f"Company with ticker symbol '{obj_in.ticker_symbol}' already exists.")

        # Validate ISIN constraint if ISIN is changed
        if obj_in.isin and obj_in.isin != company.isin:
            existing = await self.repository.get_by_isin(obj_in.isin)
            if existing:
                raise ValueError(f"Company with ISIN '{obj_in.isin}' already exists.")

        updated = await self.repository.update(db_obj=company, obj_in=obj_in)
        # Invalidate cache
        await cache.delete(f"company:id:{id}")
        return updated

    async def delete_company(self, id: UUID) -> Company:
        """Delete a company and invalidate cache."""
        from app.core.cache import cache
        company = await self.get_company(id)
        await self.repository.remove(id=id)
        # Invalidate cache
        await cache.delete(f"company:id:{id}")
        return company

