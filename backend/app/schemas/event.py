from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class EventAnalyzeRequest(BaseModel):
    """
    Validation schema for submitting a corporate or market event for impact analysis.
    """
    title: str = Field(..., description="Title of the event (e.g. 'Federal Reserve Interest Rate Cut')")
    description: str = Field(..., description="Details and context describing the event")


class Evidence(BaseModel):
    """
    Validation schema representing a grounded citation reference from ingested documents.
    """
    document_title: str = Field(..., description="Title of the cited parent document")
    page_number: int = Field(..., description="1-based page index of the document")
    section_title: Optional[str] = Field(None, description="Header section title of the chunk")
    chunk_text: str = Field(..., description="Verbatim text snippet of the chunk evidence")
    similarity_score: float = Field(..., description="Embedding match similarity score")


class CompanyImpact(BaseModel):
    """
    Validation schema detailing impact parameters for a specific registered company.
    """
    company_id: UUID = Field(..., description="Corporate database ID identifier")
    company_name: str = Field(..., description="Corporate name")
    industry: str = Field(..., description="Operating industry name")
    impact_type: str = Field(..., description="Impact direction classification (Positive Impact, Negative Impact, Neutral Impact)")
    confidence_score: float = Field(..., description="Calculated confidence score between 0.0 and 1.0")
    reasoning: str = Field(..., description="Detailed explanation text describing the impact dynamics")
    evidence: List[Evidence] = Field(default_factory=list, description="Verbatim chunks proving impact dynamics")


class EventAnalyzeResponse(BaseModel):
    """
    Structured research response mapping the full event impact profile across companies and sectors.
    """
    event_summary: str = Field(..., description="Sanitized summarization of the event description")
    event_type: str = Field(..., description="Classification category (macroeconomic, regulatory, geopolitical, etc.)")
    severity: str = Field(..., description="Calculated urgency severity (LOW, MEDIUM, HIGH, CRITICAL)")
    affected_industries: List[str] = Field(..., description="List of direct and indirect industry sector categories affected")
    potentially_impacted_companies: List[CompanyImpact] = Field(..., description="Analyzed corporate entities matching affected industries")
