import uuid
import enum
from sqlalchemy import String, Text, ForeignKey, Enum, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseModel


class ChatRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class ChatSession(BaseModel):
    """
    SQLAlchemy model representing a chat conversation session.
    Each session holds multiple user/assistant/system messages.
    """
    __tablename__ = "chat_sessions"

    ticker: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at.asc()"
    )


class ChatMessage(BaseModel):
    """
    SQLAlchemy model representing an individual message inside a ChatSession.
    """
    __tablename__ = "chat_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[ChatRole] = mapped_column(
        Enum(ChatRole, name="chatrole"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    session = relationship("ChatSession", back_populates="messages")

    # Secondary index on inherited created_at field for deterministic sorting
    __table_args__ = (
        Index("ix_chat_messages_created_at_id", "created_at", "id"),
    )
