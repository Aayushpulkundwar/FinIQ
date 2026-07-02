from typing import Any, Generic, List, Optional, Type, TypeVar
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Generic base class for database access following the Repository pattern.
    """
    def __init__(self, model: Type[ModelType], db: AsyncSession):
        self.model = model
        self.db = db

    async def get(self, id: Any) -> Optional[ModelType]:
        """Fetch a single record by primary key."""
        return await self.db.get(self.model, id)

    async def get_multi(self, *, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """Fetch multiple records with offset and limit."""
        stmt = select(self.model).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, *, obj_in: Any) -> ModelType:
        """Create a new record in the database."""
        obj_in_data = obj_in.model_dump() if hasattr(obj_in, "model_dump") else obj_in
        db_obj = self.model(**obj_in_data)
        self.db.add(db_obj)
        await self.db.flush()
        return db_obj

    async def update(self, *, db_obj: ModelType, obj_in: Any) -> ModelType:
        """Update an existing record."""
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        self.db.add(db_obj)
        await self.db.flush()
        return db_obj

    async def remove(self, *, id: Any) -> Optional[ModelType]:
        """Delete a record by ID."""
        obj = await self.db.get(self.model, id)
        if obj:
            await self.db.delete(obj)
            await self.db.flush()
        return obj
