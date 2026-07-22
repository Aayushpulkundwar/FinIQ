import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_default_config_loading():
    """Verify that settings can load with standard dev defaults."""
    config = Settings(
        ENVIRONMENT="local",
        JWT_SECRET_KEY="test-secret-key-12345678901234567890",
        OPENAI_API_KEY="test-key",
        MINIO_ENDPOINT="localhost:9000",
        MINIO_ACCESS_KEY="minioadmin",
        MINIO_SECRET_KEY="minioadmin",
    )
    assert config.PROJECT_NAME == "FinsightAI"
    assert config.ENVIRONMENT == "local"
    assert config.DEBUG is True
    # Celery Broker/Backend should be auto-assembled
    assert "redis://localhost:6379/0" in config.CELERY_BROKER_URL
    assert "redis://localhost:6379/0" in config.CELERY_RESULT_BACKEND


def test_production_config_strict_validation():
    """Verify that production environments enforce stricter security constraints."""
    # 1. Reject DEBUG=True in production
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DEBUG=True,  # Should fail
            JWT_SECRET_KEY="secure-secret-key-that-is-at-least-32-chars",
            OPENAI_API_KEY="valid-key",
            MINIO_ACCESS_KEY="secureaccess",
            MINIO_SECRET_KEY="securesecret",
        )
    assert "DEBUG mode must be false in 'production' environment" in str(exc_info.value)

    # 2. Reject default Postgres password in production
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            POSTGRES_PASSWORD="postgres",  # Default, should fail
            JWT_SECRET_KEY="secure-secret-key-that-is-at-least-32-chars",
            OPENAI_API_KEY="valid-key",
            MINIO_ACCESS_KEY="secureaccess",
            MINIO_SECRET_KEY="securesecret",
        )
    assert "Default postgres password is not allowed in 'production' environment" in str(exc_info.value)

    # 3. Reject weak JWT secret key in production
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            POSTGRES_PASSWORD="securepassword",
            JWT_SECRET_KEY="too-weak",  # Should fail
            OPENAI_API_KEY="valid-key",
            MINIO_ACCESS_KEY="secureaccess",
            MINIO_SECRET_KEY="securesecret",
        )
    assert "JWT_SECRET_KEY must be at least 32 characters long" in str(exc_info.value)

    # 4. Reject default MinIO credentials in production
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            POSTGRES_PASSWORD="securepassword",
            JWT_SECRET_KEY="secure-secret-key-that-is-at-least-32-chars",
            OPENAI_API_KEY="valid-key",
            MINIO_ACCESS_KEY="minioadmin",  # Default, should fail
            MINIO_SECRET_KEY="minioadmin",  # Default, should fail
        )
    assert "Default MinIO credentials are not allowed in 'production' environment" in str(exc_info.value)


def test_cors_origins_parsing():
    """Verify that BACKEND_CORS_ORIGINS processes lists and comma-separated strings."""
    # List format
    config_list = Settings(
        BACKEND_CORS_ORIGINS=["http://localhost:3000", "http://localhost:8000"],
        JWT_SECRET_KEY="test-secret-key-12345678901234567890",
        OPENAI_API_KEY="test-key",
    )
    assert len(config_list.BACKEND_CORS_ORIGINS) == 2
    assert str(config_list.BACKEND_CORS_ORIGINS[0]).rstrip("/") == "http://localhost:3000"

    # Comma-separated format
    config_str = Settings(
        BACKEND_CORS_ORIGINS="http://localhost:3000, http://localhost:8000",
        JWT_SECRET_KEY="test-secret-key-12345678901234567890",
        OPENAI_API_KEY="test-key",
    )
    assert len(config_str.BACKEND_CORS_ORIGINS) == 2
    assert str(config_str.BACKEND_CORS_ORIGINS[1]).rstrip("/") == "http://localhost:8000"


def test_invalid_log_level():
    """Verify that invalid log level strings raise ValidationError."""
    with pytest.raises(ValidationError):
        Settings(
            LOG_LEVEL="INVALID_LEVEL",  # Literal check should fail
            JWT_SECRET_KEY="test-secret-key-12345678901234567890",
            OPENAI_API_KEY="test-key",
        )
