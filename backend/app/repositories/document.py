from sqlalchemy.ext.asyncio import AsyncSession
from app.models.document import Document
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    """
    Repository for PostgreSQL database operations on the Document entity.
    Keeps database operations separated from service layer logic.
    """
    def __init__(self, db: AsyncSession):
        super().__init__(Document, db)
