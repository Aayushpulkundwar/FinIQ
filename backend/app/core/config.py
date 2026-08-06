import json
from typing import Any, List, Literal, Union, Optional
from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized configuration management for FinIQ.
    Loads values from environment variables or a local .env file.
    Validates variables on startup, enforcing stricter rules in staging/production.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=True,
    )

    # =================================================================---------
    # 1. App Configuration
    # =================================================================---------
    PROJECT_NAME: str = "FinIQ"
    VERSION: str = "0.1.0"
    ENVIRONMENT: Literal["local", "development", "staging", "production"] = "local"
    DEBUG: bool = True
    MAX_FILE_SIZE_BYTES: int = 200 * 1024 * 1024  # Configurable file upload size limit (200MB default)

    # =================================================================---------
    # 2. API Configuration
    # =================================================================---------
    API_V1_STR: str = "/api/v1"
    BACKEND_CORS_ORIGINS: List[Union[str, AnyHttpUrl]] = []

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> Union[List[str], str]:
        """Parses CORS origins from a comma-separated list or a JSON array string."""
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            if isinstance(v, str):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return v
        return []

    # =================================================================---------
    # 3. PostgreSQL Database Configuration
    # =================================================================---------
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "finiq"
    DATABASE_URL: Optional[str] = None

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """Async connection URI for the FastAPI application (using asyncpg)."""
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgresql://"):
                return url.replace("postgresql://", "postgresql+asyncpg://", 1)
            elif url.startswith("postgres://"):
                return url.replace("postgres://", "postgresql+asyncpg://", 1)
            return url
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def SQLALCHEMY_SYNC_DATABASE_URI(self) -> str:
        """Sync connection URI for database migrations (using psycopg2)."""
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgresql+asyncpg://"):
                return url.replace("postgresql+asyncpg://", "postgresql://", 1)
            elif url.startswith("postgres://"):
                return url.replace("postgres://", "postgresql://", 1)
            return url
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # =================================================================---------
    # 4. Redis & Celery Configuration
    # =================================================================---------
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None

    # =================================================================---------
    # 5. AI Services Configuration
    # =================================================================---------
    LLM_PROVIDER: str = "openrouter"
    EMBEDDING_PROVIDER: str = "ollama"  # Keep as 'ollama'; embeddings still served via Ollama REST API
    EMBEDDING_MODEL: str = "bge-m3"    # BGE-M3 via Ollama (run: ollama pull bge-m3)
    EMBEDDING_BATCH_DELAY_SECONDS: int = 4
    EMBEDDING_SUB_BATCH_SIZE: int = 10
    ALLOW_MOCK_LLM: bool = False

    # Ollama settings (used for embeddings via /api/embed and LLM generation fallback)
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    OLLAMA_MODEL: str = "llama3:8b"
    OLLAMA_GENERATION_ENABLED: bool = True
    OLLAMA_GENERATION_MODEL: str = "llama3:8b"

    # API Keys
    OPENROUTER_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = "openrouter/free"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # APITube settings (legacy/optional)
    APITUBE_API_KEY: Optional[str] = None
    APITUBE_BASE_URL: str = "https://api.apitube.io"

    # RSS News configuration
    RSS_NEWS_FRESHNESS_DAYS: int = 14
    RSS_NEWS_MAX_RESULTS: int = 10
    RSS_FEED_URLS: List[str] = [
        "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "https://www.moneycontrol.com/rss/MCtopnews.xml",
        "https://www.business-standard.com/rss/companies-101.rss",
    ]

    # NVIDIA Nemotron Parse v1.2 & OCR Subsystem Configuration
    NEMOTRON_HOST: str = "34.100.175.30"
    NEMOTRON_PORT: int = 8001
    NEMOTRON_MODEL: str = "nvidia/NVIDIA-Nemotron-Parse-v1.2"
    NEMOTRON_API_KEY: Optional[str] = None
    OCR_PAGE_TEXT_THRESHOLD: int = 80
    OCR_MAX_CONCURRENT_REQUESTS: int = 5
    OCR_CACHE_ENABLED: bool = True
    OCR_CACHE_DIR: str = ".cache/ocr"
    OCR_RETRY_COUNT: int = 3
    OCR_RETRY_BACKOFF: float = 2.0
    OCR_IMAGE_DPI: int = 200

    # Primary LLM provider selection (now exclusively openrouter)
    PRIMARY_LLM_PROVIDER: str = "openrouter"

    # =================================================================---------
    # 6. JWT Authentication Configuration
    # =================================================================---------
    JWT_SECRET_KEY: str = "placeholder-jwt-secret-key-for-local-dev-only"
    SECRET_KEY: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # =================================================================---------
    # 7. MinIO Object Storage Configuration
    # =================================================================---------
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_ROOT_USER: Optional[str] = None
    MINIO_ROOT_PASSWORD: Optional[str] = None
    MINIO_BUCKET_NAME: str = "finiq-documents"
    MINIO_SECURE: bool = False

    # =================================================================---------
    # 8. Logging Configuration
    # =================================================================---------
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # =================================================================---------
    # Validation & Post-Instantiation Assembly
    # =================================================================---------
    @model_validator(mode="after")
    def assemble_urls_and_validate_production(self) -> "Settings":
        """
        Post-initialization validator:
        1. Auto-assembles Celery Broker/Backend URLs if they are not provided explicitly.
        2. Enforces strict production checks to satisfy the 12-Factor App design.
        """
        # Aliases and Fallbacks
        if self.SECRET_KEY and self.JWT_SECRET_KEY == "placeholder-jwt-secret-key-for-local-dev-only":
            self.JWT_SECRET_KEY = self.SECRET_KEY
        if self.MINIO_ROOT_USER and self.MINIO_ACCESS_KEY == "minioadmin":
            self.MINIO_ACCESS_KEY = self.MINIO_ROOT_USER
        if self.MINIO_ROOT_PASSWORD and self.MINIO_SECRET_KEY == "minioadmin":
            self.MINIO_SECRET_KEY = self.MINIO_ROOT_PASSWORD

        # 1. Celery dynamic URLs setup
        password_part = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = f"redis://{password_part}{self.REDIS_HOST}:{self.REDIS_PORT}/0"
        if not self.CELERY_RESULT_BACKEND:
            self.CELERY_RESULT_BACKEND = f"redis://{password_part}{self.REDIS_HOST}:{self.REDIS_PORT}/0"

        # 2. Strict Staging & Production checks
        if self.ENVIRONMENT in ("production", "staging"):
            if self.DEBUG:
                raise ValueError(
                    f"DEBUG mode must be false in '{self.ENVIRONMENT}' environment."
                )

            if self.POSTGRES_PASSWORD == "postgres":
                raise ValueError(
                    f"Default postgres password is not allowed in '{self.ENVIRONMENT}' environment."
                )

            if self.JWT_SECRET_KEY == "placeholder-jwt-secret-key-for-local-dev-only":
                raise ValueError(
                    f"JWT_SECRET_KEY must be set to a cryptographically secure key in '{self.ENVIRONMENT}' environment."
                )
            if len(self.JWT_SECRET_KEY) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must be at least 32 characters long to be secure."
                )

            # Removed strict LLM configuration validation from settings assembly.
            # Lifespan startup check in main.py will perform soft-fail validation.
            pass

            if self.MINIO_ACCESS_KEY == "minioadmin" or self.MINIO_SECRET_KEY == "minioadmin":
                raise ValueError(
                    f"Default MinIO credentials are not allowed in '{self.ENVIRONMENT}' environment."
                )

        return self


# Create settings singleton for application-wide use
settings = Settings()
