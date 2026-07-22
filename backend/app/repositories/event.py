from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.event import Event, Industry
from app.repositories.base import BaseRepository


class EventRepository(BaseRepository[Event]):
    """
    Repository for PostgreSQL database operations on the Event entity.
    Maintains decoupling of transaction logic.
    """
    def __init__(self, db: AsyncSession):
        super().__init__(Event, db)

    async def get_or_create_industry(self, name: str) -> Industry:
        """
        Retrieves an Industry by name or creates it if not present.
        Enforces lowercase unique indexing constraints.
        """
        clean_name = name.strip().lower()
        stmt = select(Industry).where(Industry.name == clean_name)
        result = await self.db.execute(stmt)
        industry = result.scalars().first()

        if not industry:
            industry = Industry(name=clean_name)
            self.db.add(industry)
            await self.db.flush()

        return industry
