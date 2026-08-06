from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.models.document import DocumentType, UploadStatus, ProcessingStatus
from app.core.utils import normalize_fiscal_year


class DocumentBase(BaseModel):
    """Shared fields for Document metadata validation."""
    company_id: UUID = Field(..., description="ID of the company this document belongs to")
    title: str = Field(..., max_length=255, description="Document title")
    document_type: DocumentType = Field(..., description="Type of document")
    fiscal_year: int = Field(..., description="Fiscal year (e.g. 2026)")
    quarter: Optional[int] = Field(None, ge=1, le=4, description="Fiscal quarter (1-4, nullable)")

    @field_validator("fiscal_year", mode="before")
    @classmethod
    def _normalize_fy(cls, v):
        return normalize_fiscal_year(v)


class DocumentCreate(DocumentBase):
    """Fields to construct a new Document record."""
    file_name: str
    file_path: str
    file_size: int
    mime_type: str
    upload_status: Optional[UploadStatus] = UploadStatus.pending
    processing_status: Optional[ProcessingStatus] = ProcessingStatus.pending
    file_hash: Optional[str] = None


class DocumentUpdate(BaseModel):
    """Fields for updating a Document record. All are optional."""
    title: Optional[str] = Field(None, max_length=255)
    document_type: Optional[DocumentType] = None
    fiscal_year: Optional[int] = None
    quarter: Optional[int] = Field(None, ge=1, le=4)
    upload_status: Optional[UploadStatus] = None
    processing_status: Optional[ProcessingStatus] = None


class DocumentInDBBase(DocumentBase):
    """Representing model fields stored in the database."""
    id: UUID
    file_name: str
    file_path: str
    file_size: int
    mime_type: str
    upload_status: UploadStatus
    processing_status: ProcessingStatus
    uploaded_at: datetime
    created_at: datetime
    updated_at: datetime
    file_hash: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class Document(DocumentInDBBase):
    """Representing response returned to the client."""
    pass
