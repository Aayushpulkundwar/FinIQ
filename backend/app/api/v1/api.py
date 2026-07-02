from fastapi import APIRouter
from app.api.v1.routers import auth, chat, company, document, event, health, news

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(chat.router, prefix="/chat", tags=["AI Chat"])
api_router.include_router(company.router, prefix="/company", tags=["Company Data"])
api_router.include_router(document.router, prefix="/document", tags=["Document Knowledge"])
api_router.include_router(event.router, prefix="/event", tags=["Market Events"])
api_router.include_router(news.router, prefix="/news", tags=["News Feed"])
