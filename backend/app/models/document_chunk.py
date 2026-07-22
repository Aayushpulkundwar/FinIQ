import uuid
from typing import Optional
from sqlalchemy import ForeignKey, String, JSON, Integer, Enum as SQLEnum, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from app.models.base import BaseModel
from app.models.document import DocumentType



class DocumentChunk(BaseModel):
    """
    SQLAlchemy model representing a chunk of document text and its vector embedding.
    Uses pgvector for vector storage (1024 dimensions for BGE-M3 embeddings via Ollama).
    Stores dedicated columns for frequently queried metadata.
    """
    __tablename__ = "document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_text: Mapped[str] = mapped_column(String, nullable=False)
    embedding: Mapped[list] = mapped_column(Vector(1024), nullable=False)
    is_mock_embedding: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", default=False)

    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(
        SQLEnum(DocumentType, name="documenttype"), nullable=False, index=True
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    section_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    document = relationship("Document", backref="chunks")
