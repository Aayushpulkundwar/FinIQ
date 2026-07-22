from fastapi import APIRouter
from app.api.v1.routers import auth, chat, company, document, event, financial, investment, health, news, retrieval, market, portfolio

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(chat.router, prefix="/chat", tags=["AI Chat"])
api_router.include_router(company.router, prefix="/companies", tags=["Company Data"])
api_router.include_router(document.router, prefix="/documents", tags=["Document Knowledge"])
api_router.include_router(retrieval.router, prefix="/retrieval", tags=["Retrieval"])
api_router.include_router(event.router, prefix="/events", tags=["Market Events"])
api_router.include_router(financial.router, prefix="/financial", tags=["Financial Intelligence"])
api_router.include_router(investment.router, prefix="/investment", tags=["Investment Analysis"])
api_router.include_router(news.router, prefix="/news", tags=["News Feed"])
api_router.include_router(market.router, prefix="/market", tags=["Market Intelligence"])
api_router.include_router(portfolio.router, prefix="/portfolio", tags=["Portfolio Intelligence"])

