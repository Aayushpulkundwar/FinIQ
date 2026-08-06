from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, HttpUrl, Field


class NewsArticle(BaseModel):
    id: str = Field(..., description="Unique article ID or URL hash")
    title: str = Field(..., description="Article title / headline")
    snippet: Optional[str] = Field(None, description="Short summary or excerpt of the article")
    source: str = Field(..., description="News publisher / source name")
    url: str = Field(..., description="Canonical article link")
    image_url: Optional[str] = Field(None, description="Featured article image URL if available")
    published_at: datetime = Field(..., description="Publication ISO timestamp")


class CompanyNewsResponse(BaseModel):
    company_id: UUID
    company_name: str
    ticker_symbol: str
    articles: List[NewsArticle]
