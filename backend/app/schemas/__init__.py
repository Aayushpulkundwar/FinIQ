from pydantic import BaseModel
from app.schemas.company import Company, CompanyCreate, CompanyUpdate, CompanyBase
from app.schemas.health import HealthCheckResponse, ServicesHealth
from app.schemas.document import Document, DocumentCreate, DocumentUpdate, DocumentBase
from app.schemas.retrieval import RetrievalRequest, RetrievalResponse
from app.schemas.chat import ChatQueryRequest, ChatQueryResponse
from app.schemas.response_generation import AIResponse
from app.schemas.event import EventAnalyzeRequest, EventAnalyzeResponse, CompanyImpact, Evidence as EventEvidence
from app.schemas.financial import (
    FinancialAnalyzeRequest, FinancialAnalyzeResponse,
    FinancialStatementData, FinancialMetricsData,
    FinancialFieldEvidence, MetricProvenance, TrendPoint
)
from app.schemas.investment import (
    InvestmentAnalyzeRequest, InvestmentAnalyzeResponse,
    ValuationSummary, WaccDetails, DcfDetails, SensitivityPoint
)
from app.schemas.market import (
    NewsIngestionRequest, NewsIngestionResponse, NewsArticleOut,
    MarketAnalyzeRequest, MarketAnalyzeResponse, SentimentBreakdown
)
from app.schemas.portfolio import (
    WatchlistCreate, WatchlistAddCompany, WatchlistItemOut, WatchlistOut,
    PortfolioCreate, HoldingCreate, HoldingOut, PortfolioOut,
    AllocationItem, PortfolioAnalysisResponse, PortfolioRecommendationResponse
)
from app.schemas.news import NewsArticle, CompanyNewsResponse
from app.schemas.user import (
    UserRegister, UserLogin, TokenResponse, RefreshRequest, TokenRefreshResponse, UserOut
)



class Msg(BaseModel):
    """Simple message response schema."""
    msg: str
