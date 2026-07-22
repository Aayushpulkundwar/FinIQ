import uuid
import enum
from decimal import Decimal
from datetime import datetime
from sqlalchemy import String, Text, Integer, Numeric, DateTime, Float, Enum as SQLEnum, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseModel


class PeriodType(str, enum.Enum):
    annual = "annual"
    q1 = "q1"
    q2 = "q2"
    q3 = "q3"
    q4 = "q4"


class FinancialPeriod(BaseModel):
    """Represents a fiscal reporting period for a company."""
    __tablename__ = "financial_periods"

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    period_type: Mapped[PeriodType] = mapped_column(
        SQLEnum(PeriodType, name="periodtype"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")

    # Relationships
    statements = relationship("FinancialStatement", back_populates="period", cascade="all, delete-orphan")


class FinancialStatement(BaseModel):
    """Normalized financial statement line items for a specific period."""
    __tablename__ = "financial_statements"

    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_periods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Income Statement
    revenue: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=True)
    ebitda: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=True)
    operating_income: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=True)
    net_profit: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=True)
    eps: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)

    # Balance Sheet
    total_assets: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=True)
    total_liabilities: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=True)
    shareholders_equity: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=True)

    # Cash Flow
    operating_cash_flow: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=True)
    free_cash_flow: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=True)
    capex: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=True)

    # Relationships
    period = relationship("FinancialPeriod", back_populates="statements")
    metrics = relationship("FinancialMetric", back_populates="statement", cascade="all, delete-orphan")
    evidence = relationship("FinancialEvidence", back_populates="statement", cascade="all, delete-orphan")


class FinancialMetric(BaseModel):
    """Calculated financial ratios and metrics derived from a FinancialStatement."""
    __tablename__ = "financial_metrics"

    statement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_statements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    revenue_growth_yoy: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    ebitda_margin: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    net_profit_margin: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    roe: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    roce: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    debt_to_equity: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    current_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    free_cash_flow_yield: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    eps_growth: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)

    # Relationships
    statement = relationship("FinancialStatement", back_populates="metrics")
    provenance = relationship("FinancialMetricProvenance", back_populates="metric", cascade="all, delete-orphan")


class FinancialEvidence(BaseModel):
    """Per-field source citation for every extracted financial value."""
    __tablename__ = "financial_evidence"

    statement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_statements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    financial_field: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    extracted_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=True)
    document_title: Mapped[str] = mapped_column(String(500), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    section_title: Mapped[str] = mapped_column(String(500), nullable=True)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)

    # Relationships
    statement = relationship("FinancialStatement", back_populates="evidence")


class FinancialMetricProvenance(BaseModel):
    """Tracks the formula and input fields used to calculate each financial metric."""
    __tablename__ = "financial_metric_provenance"

    metric_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_metrics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    formula: Mapped[str] = mapped_column(String(500), nullable=False)
    input_fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Relationships
    metric = relationship("FinancialMetric", back_populates="provenance")
