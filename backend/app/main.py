from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.exceptions import setup_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import ObservabilityMiddleware

# Setup centralized logging immediately on startup
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup tasks
    provider = settings.LLM_PROVIDER
    logger.info(f"Selected LLM provider: {provider}")

    # Check OpenRouter API Key loading
    key = settings.OPENROUTER_API_KEY
    key_loaded = bool(key and key.strip() != "")
    key_len = len(key) if key else 0

    logger.info(f"OpenRouter API key loaded: {key_loaded}")
    logger.info(f"OpenRouter API key length: {key_len}")

    is_valid = False
    validation_error_reason = ""

    if settings.LLM_PROVIDER.lower() == "openrouter":
        if not key_loaded:
            validation_error_reason = "OpenRouter API key is missing or empty in the environment configuration."
        elif "placeholder" in key.lower():
            validation_error_reason = "OpenRouter API key is set to a placeholder value."
        else:
            is_valid = True
    else:
        validation_error_reason = f"Provider '{settings.LLM_PROVIDER}' is not supported as the primary LLM provider."

    if not is_valid:
        # Log a clear error explaining why validation failed
        logger.error(
            f"Startup Validation Error: No valid credentials configured for OpenRouter. "
            f"Reason: {validation_error_reason} AI Response Generation is disabled."
        )
    else:
        logger.info("OpenRouter provider initialized successfully.")

    logger.info("FinIQ Backend application initialized successfully.")
    yield
    # Shutdown tasks
    logger.info("FinIQ Backend application shutting down.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Observability JSON logs & correlation headers middleware
app.add_middleware(ObservabilityMiddleware)

# Global Exception Handlers Setup
setup_exception_handlers(app)

# Include application routers
from app.api.v1.routers.company import financials_router
app.include_router(financials_router)
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Root"])
async def root() -> dict:
    """Welcome root message API."""
    return {
        "message": "Welcome to FinIQ Investment Research Platform API!",
        "docs": "/docs",
    }
