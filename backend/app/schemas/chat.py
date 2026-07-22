import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.response_generation import AIResponse


class ChatQueryRequest(BaseModel):
    """
    Validation schema for executing the orchestrator query.
    """
    query: str = Field(..., description="The user query or prompt string")
    session_id: Optional[uuid.UUID] = Field(None, description="Optional active chat session UUID")


class ChatQueryResponse(BaseModel):
    """
    Validation schema for returning structured graph execution context.
    """
    user_query: str
    retrieved_chunks: List[Dict[str, Any]]
    company_details: Optional[Dict[str, Any]] = None
    document_metadata: List[Dict[str, Any]]
    execution_history: List[str]
    final_context: Dict[str, Any]
    response: Optional[AIResponse] = None
    session_id: uuid.UUID = Field(..., description="The UUID of the chat session associated with this query")


class ChatSessionCreateRequest(BaseModel):
    """
    Schema for creating a chat session.
    """
    ticker: Optional[str] = Field(None, description="Optional ticker symbol to bind this session to")


class ChatSessionCreateResponse(BaseModel):
    """
    Schema for returning the newly created chat session id.
    """
    session_id: uuid.UUID


class ChatMessageResponse(BaseModel):
    """
    Schema representing a single conversation message in transcript history.
    """
    id: uuid.UUID
    role: str
    content: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True

