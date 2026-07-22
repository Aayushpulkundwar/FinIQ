from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class InvestmentAnalyzeRequest(BaseModel):
    """Request schema for investment analysis and valuation."""
    company_id: UUID = Field(..., description="Target company UUID")
    fiscal_year: Optional[int] = Field(None, description="Specific fiscal year for baseline data (optional)")


class WaccDetails(BaseModel):
    """Inputs and result for Weighted Average Cost of Capital calculation."""
    cost_of_equity: float
    cost_of_debt: float
    equity_weight: float
    debt_weight: float
    wacc: float


class DcfDetails(BaseModel):
    """Detailed Discounted Cash Flow valuation projection results."""
    baseline_fcf: float
    fcf_growth_rate: float
    projected_fcfs: List[float] = Field(..., description="5-year projected Free Cash Flows")
    terminal_growth_rate: float
    terminal_value: float
    enterprise_value: float
    equity_value: float
    shares_outstanding: float
    intrinsic_share_price: float


class SensitivityPoint(BaseModel):
    """Valuation price output for a specific WACC and perpetuity growth rate variation."""
    wacc: float = Field(..., description="Discount rate used")
    growth_rate: float = Field(..., description="Terminal growth rate used")
    intrinsic_price: float = Field(..., description="Resulting intrinsic share price")


class ValuationSummary(BaseModel):
    """Consolidated valuation output from the Valuation Engine."""
    wacc_details: WaccDetails
    dcf_details: DcfDetails
    sensitivity_grid: List[SensitivityPoint] = Field(..., description="5x5 WACC/growth grid")
    confidence_score: float = Field(..., description="Quality/completeness rating between 0.0 and 1.0")
    
    # Audit intermediate inputs & flags
    beta: Optional[float] = None
    beta_source: Optional[str] = None
    wacc_clamped_due_to_fallback_beta: bool = False
    risk_free_rate: Optional[float] = None
    equity_risk_premium: Optional[float] = None
    tax_rate: Optional[float] = None
    cash: Optional[float] = None
    debt: Optional[float] = None
    market_cap: Optional[float] = None
    cost_of_debt_estimated: bool = False
    tax_rate_estimated: bool = False
    fcf_growth_estimated: bool = False
    as_of: Optional[str] = None
    currency: Optional[str] = "USD"

    # Diagnostic flags populated by the valuation wrapper.
    # Examples: "double_clamp_detected", "extreme_deviation_flagged".
    # Empty list means no anomalies detected.
    valuation_flags: List[str] = Field(default_factory=list)


class InvestmentAnalyzeResponse(BaseModel):
    """Full Investment Analysis Response containing valuation and the institutional research report."""
    company_id: UUID
    company_name: str
    valuation_summary: ValuationSummary
    intrinsic_value: float = Field(..., description="The calculated base DCF intrinsic share price")
    sensitivity_analysis: List[SensitivityPoint] = Field(..., description="Flattened sensitivity points list")
    research_report: str = Field(..., description="Institutional research report in markdown format")


class InvestmentTaskEnqueueResponse(BaseModel):
    """Initial response returned when enqueuing the background analysis task."""
    task_id: str
    status: str = Field(default="PENDING", description="The current status of the background task")


class InvestmentTaskStatusResponse(BaseModel):
    """Response returned when querying the status of a background analysis task."""
    task_id: str
    status: str
    message: Optional[str] = None
    result: Optional[InvestmentAnalyzeResponse] = None
    error: Optional[str] = None

