import json
from typing import Any, List, Literal, Union, Optional
from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized configuration management for FinsightAI.
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
    PROJECT_NAME: str = "FinsightAI"
    VERSION: str = "0.1.0"
    ENVIRONMENT: Literal["local", "development", "staging", "production"] = "local"
    DEBUG: bool = True
    MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024  # Configurable file upload size limit (10MB default)

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
    POSTGRES_DB: str = "finsightai"

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """Async connection URI for the FastAPI application (using asyncpg)."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def SQLALCHEMY_SYNC_DATABASE_URI(self) -> str:
        """Sync connection URI for database migrations (using psycopg2)."""
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

    # Ollama (used exclusively for embeddings via /api/embed — NOT for LLM generation)
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    OLLAMA_MODEL: str = "llama3:8b"

    # OpenRouter — hosted LLM API (OpenAI-compatible, replaces local phi3:mini)
    # Set OPENROUTER_API_KEY in .env. Get a key at https://openrouter.ai/keys
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = "openrouter/free"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # Primary LLM provider selection (now exclusively openrouter)
    PRIMARY_LLM_PROVIDER: str = "openrouter"

    # =================================================================---------
    # 6. JWT Authentication Configuration
    # =================================================================---------
    JWT_SECRET_KEY: str = "placeholder-jwt-secret-key-for-local-dev-only"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # =================================================================---------
    # 7. MinIO Object Storage Configuration
    # =================================================================---------
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_NAME: str = "finsightai-documents"
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
