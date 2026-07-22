# Import all the models, so that Base has them before being
# imported by Alembic.
from app.models.base import Base, BaseModel  # noqa
from app.models.company import Company  # noqa
from app.models.recent_company_selection import RecentCompanySelection  # noqa
from app.models.document import Document  # noqa
from app.models.document_chunk import DocumentChunk  # noqa
from app.models.event import Event, Industry, EventIndustry  # noqa
from app.models.financial import (  # noqa
    FinancialPeriod, FinancialStatement, FinancialMetric,
    FinancialEvidence, FinancialMetricProvenance
)
from app.models.market import NewsArticle, NewsCompany, NewsIndustry, MarketEvent  # noqa
from app.models.user import User  # noqa
from app.models.portfolio import Portfolio, PortfolioHolding, Watchlist, WatchlistItem  # noqa
from app.models.audit import AuditLog  # noqa
from app.models.chat import ChatSession, ChatMessage  # noqa
