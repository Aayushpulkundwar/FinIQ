import uuid
from datetime import datetime
from sqlalchemy import ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseModel


class RecentCompanySelection(BaseModel):
    """
    SQLAlchemy model representing a per-user recent company selection.
    Tracks user_id, company_id, and selected_at.
    """
    __tablename__ = "recent_company_selections"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    selected_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Optional relationships
    user = relationship("User", backref="recent_selections")
    company = relationship("Company", backref="recent_selections")

    __table_args__ = (
        UniqueConstraint("user_id", "company_id", name="uq_user_company_selection"),
    )
