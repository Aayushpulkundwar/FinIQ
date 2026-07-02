from typing import Generator
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock database connection for routes testing."""
    db = AsyncMock()
    # Mock typical execution for SQL healthcheck
    db.execute = AsyncMock()
    return db


@pytest.fixture
def client(mock_db: AsyncMock) -> Generator[TestClient, None, None]:
    """Test client using FastAPI TestClient with mock dependencies."""
    # Override database session dependency
    app.dependency_overrides[get_db] = lambda: mock_db

    with TestClient(app) as c:
        yield c

    # Clean up overrides
    app.dependency_overrides.clear()

