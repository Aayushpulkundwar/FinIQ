from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class FinancialAnalyzeRequest(BaseModel):
    """Request schema for financial analysis of a company."""
    company_id: UUID = Field(..., description="Target company UUID")
    fiscal_year: Optional[int] = Field(None, description="Specific fiscal year (e.g. 2025). Latest if omitted.")
    period_type: Optional[str] = Field(None, description="Period type: annual, q1, q2, q3, q4. Defaults to annual.")


class FinancialFieldEvidence(BaseModel):
    """
    Per-field source citation for each extracted financial value.
    Tracks exactly which document chunk provided the data.
    """
    financial_field: str = Field(..., description="Name of the financial line item (e.g. 'revenue')")
    extracted_value: Optional[float] = Field(None, description="The numeric value extracted")
    missing_reason: Optional[str] = Field(None, description="NOT_REPORTED | NOT_APPLICABLE | UNABLE_TO_EXTRACT")
    document_title: str = Field(..., description="Source document title")
    page_number: int = Field(..., description="Source page number")
    section_title: Optional[str] = Field(None, description="Section heading in source document")
    chunk_text: str = Field(..., description="Verbatim chunk text supporting the extraction")
    similarity_score: float = Field(..., description="Embedding similarity score of the chunk")


class FinancialStatementData(BaseModel):
    """Normalized financial statement line items."""
    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    operating_income: Optional[float] = None
    net_profit: Optional[float] = None
    eps: Optional[float] = None
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    shareholders_equity: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    free_cash_flow: Optional[float] = None
    capex: Optional[float] = None


class FinancialMetricsData(BaseModel):
    """Calculated financial ratios and metrics."""
    revenue_growth_yoy: Optional[float] = None
    ebitda_margin: Optional[float] = None
    net_profit_margin: Optional[float] = None
    roe: Optional[float] = None
    roce: Optional[float] = None
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    free_cash_flow_yield: Optional[float] = None
    eps_growth: Optional[float] = None


class MetricProvenance(BaseModel):
    """Tracks the formula and input fields used to calculate a metric."""
    metric_name: str = Field(..., description="Name of the metric (e.g. 'ebitda_margin')")
    formula: str = Field(..., description="Human-readable formula string")
    input_fields: List[str] = Field(..., description="List of field names used in calculation")


class TrendPoint(BaseModel):
    """Single period data point for trend visualization."""
    fiscal_year: int
    period_type: str
    revenue: Optional[float] = None
    net_profit: Optional[float] = None
    eps: Optional[float] = None
    trend_direction: str = Field(..., description="Increasing | Stable | Declining")


class FinancialAnalyzeResponse(BaseModel):
    """Full financial intelligence analysis response."""
    company_id: UUID
    company_name: str
    fiscal_year: int
    period_type: str
    currency: str
    financial_summary: str
    latest_statement: FinancialStatementData
    calculated_metrics: FinancialMetricsData
    
    # Duplicate properties for frontend compatibility
    statements: Optional[FinancialStatementData] = None
    metrics: Optional[FinancialMetricsData] = None
    
    trend_analysis: List[TrendPoint]
    metric_provenance: List[MetricProvenance]
    financial_evidence: List[FinancialFieldEvidence]
    reporting_status: Optional[str] = None

