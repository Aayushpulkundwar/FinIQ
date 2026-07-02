from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.exceptions import setup_exception_handlers
from app.core.logging import setup_logging

# Setup centralized logging immediately on startup
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup tasks
    logger.info("FinsightAI Backend application initialized successfully.")
    yield
    # Shutdown tasks
    logger.info("FinsightAI Backend application shutting down.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# Global Exception Handlers Setup
setup_exception_handlers(app)

# CORS configuration
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            str(origin).rstrip("/") for origin in settings.BACKEND_CORS_ORIGINS
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include application routers
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Root"])
async def root() -> dict:
    """Welcome root message API."""
    return {
        "message": "Welcome to FinsightAI Investment Research Platform API!",
        "docs": "/docs",
    }
