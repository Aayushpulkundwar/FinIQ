from datetime import datetime
import enum
import uuid
from typing import Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseModel


class DocumentType(str, enum.Enum):
    annual_report = "annual_report"
    quarterly_report = "quarterly_report"
    investor_presentation = "investor_presentation"
    earnings_call = "earnings_call"
    other = "other"


class UploadStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"


class ProcessingStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Document(BaseModel):
    """
    SQLAlchemy model representing a Document metadata entry in the FinsightAI platform.
    Inherits primary key (UUID) and standard timestamps from BaseModel.
    """
    __tablename__ = "documents"

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(
        SQLEnum(DocumentType, name="documenttype"), nullable=False, index=True
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    upload_status: Mapped[UploadStatus] = mapped_column(
        SQLEnum(UploadStatus, name="uploadstatus"),
        default=UploadStatus.pending,
        nullable=False,
    )
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        SQLEnum(ProcessingStatus, name="processingstatus"),
        default=ProcessingStatus.pending,
        nullable=False,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True)

    company = relationship("Company", backref="documents")
