import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Text, DateTime, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseModel


class EventType(str, enum.Enum):
    macroeconomic = "macroeconomic"
    policy = "policy"
    regulatory = "regulatory"
    geopolitical = "geopolitical"
    industry = "industry"
    company_specific = "company_specific"


class EventSeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Industry(BaseModel):
    """
    SQLAlchemy model representing industry categories.
    """
    __tablename__ = "industries"

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)


class Event(BaseModel):
    """
    SQLAlchemy model representing market, geopolitical, regulatory, or macroeconomic events.
    """
    __tablename__ = "events"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[EventType] = mapped_column(
        SQLEnum(EventType, name="eventtype"), nullable=False, index=True
    )
    severity: Mapped[EventSeverity] = mapped_column(
        SQLEnum(EventSeverity, name="eventseverity"), nullable=False, index=True
    )
    event_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Many-to-many relationship to Industry
    industries = relationship(
        "Industry",
        secondary="event_industries",
        backref="events"
    )


class EventIndustry(BaseModel):
    """
    SQLAlchemy association table mapping Events to Industries.
    """
    __tablename__ = "event_industries"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    industry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("industries.id", ondelete="CASCADE"), primary_key=True
    )
