from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from app.models.document import DocumentType


class RetrievalRequest(BaseModel):
    """
    Validation schema for knowledge retrieval query requests.
    """
    query: str = Field(..., description="Query search term or question to execute semantic similarity against")
    top_k: int = Field(5, ge=1, le=50, description="Maximum number of document chunks to return")
    minimum_similarity: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Optional minimum cosine similarity score threshold (0.0 to 1.0)"
    )
    company_id: Optional[UUID] = Field(None, description="Optional filter by specific corporate ID")
    document_type: Optional[DocumentType] = Field(None, description="Optional filter by document type classification")
    fiscal_year: Optional[int] = Field(None, description="Optional filter by corporate fiscal year")
    page_number: Optional[int] = Field(None, ge=1, description="Optional filter by physical document page index")


class RetrievalResponse(BaseModel):
    """
    Validation schema for returning ranked vector matching segments.
    """
    chunk_text: str = Field(..., description="Text segment block")
    similarity_score: float = Field(..., description="Cosine similarity score (higher is more relevant)")
    document_id: UUID = Field(..., description="UUID reference of the parent document")
    document_title: str = Field(..., description="Title of the parent document")
    company_id: UUID = Field(..., description="UUID reference of the target company")
    page_number: int = Field(..., description="1-based page index of this chunk")
    chunk_index: int = Field(..., description="0-based ordering sequence chunk index")
    section_title: Optional[str] = Field(None, description="Header section title if available")
    document_type: DocumentType = Field(..., description="Parent document category")
    fiscal_year: int = Field(..., description="Ingested report fiscal year")

    model_config = ConfigDict(from_attributes=True)
