from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator

INVALID_PLACEHOLDERS = {"string", "test", "placeholder", "none", "null", "n/a", "undefined"}


class CompanyBase(BaseModel):
    """Shared fields for Company, validates request and response payloads."""
    company_name: str = Field(
        ..., min_length=1, max_length=255, description="Full legal name of the company"
    )
    ticker_symbol: str = Field(
        ..., min_length=1, max_length=50, description="Unique stock ticker symbol"
    )
    exchange: str = Field(
        ..., min_length=1, max_length=100, description="Exchange listing (e.g. NYSE, NASDAQ)"
    )
    sector: str = Field(
        ..., min_length=1, max_length=100, description="Company's primary economic sector"
    )
    industry: str = Field(
        ..., min_length=1, max_length=100, description="Company's specific industry class"
    )
    isin: str = Field(
        ..., min_length=1, max_length=50, description="Unique International Securities Identification Number"
    )
    website: Optional[str] = Field(
        None, max_length=255, description="Official company website URL"
    )
    peer_tickers: Optional[str] = Field(
        None, description="Comma-separated list of peer tickers"
    )

    @field_validator("company_name", "ticker_symbol", "exchange", "isin", mode="before")
    @classmethod
    def validate_not_placeholder(cls, v: str) -> str:
        if isinstance(v, str) and v.strip().lower() in INVALID_PLACEHOLDERS:
            raise ValueError(f"'{v}' is an invalid placeholder value")
        return v


class CompanyCreate(CompanyBase):
    """Properties to receive on Company creation."""
    pass


class CompanyUpdate(BaseModel):
    """Properties to receive on Company update. All fields are optional."""
    company_name: Optional[str] = Field(None, min_length=1, max_length=255)
    ticker_symbol: Optional[str] = Field(None, min_length=1, max_length=50)
    exchange: Optional[str] = Field(None, min_length=1, max_length=100)
    sector: Optional[str] = Field(None, min_length=1, max_length=100)
    industry: Optional[str] = Field(None, min_length=1, max_length=100)
    isin: Optional[str] = Field(None, min_length=1, max_length=50)
    website: Optional[str] = Field(None, max_length=255)


class CompanyInDBBase(CompanyBase):
    """Schema representing model fields stored in the database."""
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Company(CompanyInDBBase):
    """Properties to return to client."""
    pass
