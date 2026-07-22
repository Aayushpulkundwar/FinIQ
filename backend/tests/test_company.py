import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from fastapi.testclient import TestClient
from app.models.company import Company
from app.services.company import CompanyService
from app.schemas.company import CompanyCreate, CompanyUpdate


@pytest.mark.asyncio
async def test_company_service_create_success():
    """Verify that CompanyService can create a company successfully when no duplicates exist."""
    db_mock = AsyncMock()
    service = CompanyService(db_mock)
    service.repository = AsyncMock()
    service.repository.get_by_ticker.return_value = None
    service.repository.get_by_isin.return_value = None

    company_id = uuid4()
    now = datetime.utcnow()
    mock_company = Company(
        id=company_id,
        company_name="Test Company",
        ticker_symbol="TST",
        exchange="NYSE",
        sector="Technology",
        industry="Software",
        isin="US1234567890",
        website="https://test.com",
        created_at=now,
        updated_at=now,
    )
    service.repository.create.return_value = mock_company

    obj_in = CompanyCreate(
        company_name="Test Company",
        ticker_symbol="TST",
        exchange="NYSE",
        sector="Technology",
        industry="Software",
        isin="US1234567890",
        website="https://test.com"
    )

    result = await service.create_company(obj_in)
    assert result.id == company_id
    assert result.company_name == "Test Company"
    service.repository.create.assert_called_once_with(obj_in=obj_in)


@pytest.mark.asyncio
async def test_company_service_create_duplicate_ticker():
    """Verify that CompanyService raises ValueError on duplicate ticker."""
    db_mock = AsyncMock()
    service = CompanyService(db_mock)
    service.repository = AsyncMock()
    service.repository.get_by_ticker.return_value = Company(
        ticker_symbol="TST",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    obj_in = CompanyCreate(
        company_name="Test Company",
        ticker_symbol="TST",
        exchange="NYSE",
        sector="Technology",
        industry="Software",
        isin="US1234567890",
        website="https://test.com"
    )

    with pytest.raises(ValueError) as exc_info:
        await service.create_company(obj_in)
    assert "ticker symbol 'TST' already exists" in str(exc_info.value)


@pytest.mark.asyncio
async def test_company_service_create_duplicate_isin():
    """Verify that CompanyService raises ValueError on duplicate ISIN."""
    db_mock = AsyncMock()
    service = CompanyService(db_mock)
    service.repository = AsyncMock()
    service.repository.get_by_ticker.return_value = None
    service.repository.get_by_isin.return_value = Company(
        isin="US1234567890",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    obj_in = CompanyCreate(
        company_name="Test Company",
        ticker_symbol="TST",
        exchange="NYSE",
        sector="Technology",
        industry="Software",
        isin="US1234567890",
        website="https://test.com"
    )

    with pytest.raises(ValueError) as exc_info:
        await service.create_company(obj_in)
    assert "ISIN 'US1234567890' already exists" in str(exc_info.value)


def test_api_create_company(client: TestClient):
    """Test the POST /companies endpoint."""
    company_id = uuid4()
    now = datetime.utcnow()
    with patch("app.api.v1.routers.company.CompanyService") as MockService:
        instance = MockService.return_value
        instance.create_company = AsyncMock(return_value=Company(
            id=company_id,
            company_name="Test Company",
            ticker_symbol="TST",
            exchange="NYSE",
            sector="Technology",
            industry="Software",
            isin="US1234567890",
            website="https://test.com",
            created_at=now,
            updated_at=now,
        ))

        payload = {
            "company_name": "Test Company",
            "ticker_symbol": "TST",
            "exchange": "NYSE",
            "sector": "Technology",
            "industry": "Software",
            "isin": "US1234567890",
            "website": "https://test.com"
        }

        response = client.post("/api/v1/companies", json=payload)
        assert response.status_code == 201
        assert response.json()["ticker_symbol"] == "TST"


def test_api_list_companies(client: TestClient):
    """Test the GET /companies endpoint."""
    company_id = uuid4()
    now = datetime.utcnow()
    with patch("app.api.v1.routers.company.CompanyService") as MockService:
        instance = MockService.return_value
        instance.list_companies = AsyncMock(return_value=[
            Company(
                id=company_id,
                company_name="Test Company",
                ticker_symbol="TST",
                exchange="NYSE",
                sector="Technology",
                industry="Software",
                isin="US1234567890",
                website="https://test.com",
                created_at=now,
                updated_at=now,
            )
        ])

        response = client.get("/api/v1/companies")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["ticker_symbol"] == "TST"


def test_api_get_company(client: TestClient):
    """Test the GET /companies/{id} endpoint."""
    company_id = uuid4()
    now = datetime.utcnow()
    with patch("app.api.v1.routers.company.CompanyService") as MockService:
        instance = MockService.return_value
        instance.get_company = AsyncMock(return_value=Company(
            id=company_id,
            company_name="Test Company",
            ticker_symbol="TST",
            exchange="NYSE",
            sector="Technology",
            industry="Software",
            isin="US1234567890",
            website="https://test.com",
            created_at=now,
            updated_at=now,
        ))

        response = client.get(f"/api/v1/companies/{company_id}")
        assert response.status_code == 200
        assert response.json()["id"] == str(company_id)


def test_api_get_company_not_found(client: TestClient):
    """Test the GET /companies/{id} endpoint when company is not found."""
    company_id = uuid4()
    with patch("app.api.v1.routers.company.CompanyService") as MockService:
        instance = MockService.return_value
        instance.get_company = AsyncMock(side_effect=KeyError("Company not found"))

        response = client.get(f"/api/v1/companies/{company_id}")
        assert response.status_code == 404
        assert "Company not found" in response.json()["detail"]


def test_api_update_company(client: TestClient):
    """Test the PUT /companies/{id} endpoint."""
    company_id = uuid4()
    now = datetime.utcnow()
    with patch("app.api.v1.routers.company.CompanyService") as MockService:
        instance = MockService.return_value
        instance.update_company = AsyncMock(return_value=Company(
            id=company_id,
            company_name="Updated Company",
            ticker_symbol="TST",
            exchange="NYSE",
            sector="Technology",
            industry="Software",
            isin="US1234567890",
            website="https://test.com",
            created_at=now,
            updated_at=now,
        ))

        payload = {"company_name": "Updated Company"}
        response = client.put(f"/api/v1/companies/{company_id}", json=payload)
        assert response.status_code == 200
        assert response.json()["company_name"] == "Updated Company"


def test_api_delete_company(client: TestClient):
    """Test the DELETE /companies/{id} endpoint."""
    company_id = uuid4()
    now = datetime.utcnow()
    with patch("app.api.v1.routers.company.CompanyService") as MockService:
        instance = MockService.return_value
        instance.delete_company = AsyncMock(return_value=Company(
            id=company_id,
            company_name="Test Company",
            ticker_symbol="TST",
            exchange="NYSE",
            sector="Technology",
            industry="Software",
            isin="US1234567890",
            website="https://test.com",
            created_at=now,
            updated_at=now,
        ))

        response = client.delete(f"/api/v1/companies/{company_id}")
        assert response.status_code == 200
        assert response.json()["id"] == str(company_id)


def test_api_search_companies(client: TestClient, mock_db: AsyncMock):
    """Test GET /companies/search endpoint."""
    from unittest.mock import MagicMock
    company_id = uuid4()
    now = datetime.utcnow()
    mock_company = Company(
        id=company_id,
        company_name="Test Company",
        ticker_symbol="TST",
        exchange="NYSE",
        sector="Technology",
        industry="Software",
        isin="US1234567890",
        website="https://test.com",
        created_at=now,
        updated_at=now,
    )
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_company]
    mock_db.execute.return_value = mock_result

    response = client.get("/api/v1/companies/search?q=TST")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ticker_symbol"] == "TST"


def test_api_get_recent_companies(client: TestClient, mock_db: AsyncMock):
    """Test GET /companies/recent endpoint."""
    from unittest.mock import MagicMock
    from app.models.user import User as UserModel
    mock_user = UserModel(
        id=uuid4(),
        email="test@test.com",
        hashed_password="hash",
        is_active=True
    )
    company_id = uuid4()
    now = datetime.utcnow()
    mock_company = Company(
        id=company_id,
        company_name="Test Company",
        ticker_symbol="TST",
        exchange="NYSE",
        sector="Technology",
        industry="Software",
        isin="US1234567890",
        website="https://test.com",
        created_at=now,
        updated_at=now,
    )

    mock_result_user = MagicMock()
    mock_result_user.scalars.return_value.first.return_value = mock_user

    mock_result_comp = MagicMock()
    mock_result_comp.scalars.return_value.all.return_value = [mock_company]

    mock_db.execute.side_effect = [mock_result_user, mock_result_comp]

    response = client.get("/api/v1/companies/recent")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ticker_symbol"] == "TST"


def test_api_select_company(client: TestClient, mock_db: AsyncMock):
    """Test POST /companies/{id}/select endpoint."""
    from unittest.mock import MagicMock
    company_id = uuid4()
    now = datetime.utcnow()
    
    with patch("app.api.v1.routers.company.CompanyService") as MockService:
        instance = MockService.return_value
        instance.get_company = AsyncMock(return_value=Company(
            id=company_id,
            company_name="Test Company",
            ticker_symbol="TST",
            exchange="NYSE",
            sector="Technology",
            industry="Software",
            isin="US1234567890",
            created_at=now,
            updated_at=now,
        ))

        from app.models.user import User as UserModel
        mock_user = UserModel(id=uuid4(), email="test@test.com", hashed_password="hash", is_active=True)
        
        mock_result_user = MagicMock()
        mock_result_user.scalars.return_value.first.return_value = mock_user

        mock_result_selection = MagicMock()
        mock_result_selection.scalars.return_value.first.return_value = None

        mock_db.execute.side_effect = [mock_result_user, mock_result_selection]

        response = client.post(f"/api/v1/companies/{company_id}/select")
        assert response.status_code == 200
        assert response.json()["status"] == "success"


@patch("yfinance.Ticker")
def test_api_get_company_live_price(mock_ticker, client: TestClient):
    """Test GET /companies/{id}/live-price endpoint."""
    company_id = uuid4()
    now = datetime.utcnow()
    with patch("app.api.v1.routers.company.CompanyService") as MockService:
        instance = MockService.return_value
        instance.get_company = AsyncMock(return_value=Company(
            id=company_id,
            company_name="Test Company",
            ticker_symbol="TST",
            exchange="NYSE",
            sector="Technology",
            industry="Software",
            isin="US1234567890",
            created_at=now,
            updated_at=now,
        ))

        mock_instance = mock_ticker.return_value
        mock_instance.info = {
            "currentPrice": 150.0,
            "open": 149.0,
            "dayHigh": 152.0,
            "dayLow": 148.0,
            "volume": 1000000
        }
        
        import pandas as pd
        df = pd.DataFrame([{"Close": 150.0}], index=[pd.Timestamp.now()])
        mock_instance.history.return_value = df

        response = client.get(f"/api/v1/companies/{company_id}/live-price")
        assert response.status_code == 200
        data = response.json()
        assert data["current_price"] == 150.0
        assert data["ticker"] == "TST"


@patch("yfinance.Ticker")
def test_api_get_company_history(mock_ticker, client: TestClient):
    """Test GET /companies/{id}/history endpoint."""
    company_id = uuid4()
    now = datetime.utcnow()
    with patch("app.api.v1.routers.company.CompanyService") as MockService:
        instance = MockService.return_value
        instance.get_company = AsyncMock(return_value=Company(
            id=company_id,
            company_name="Test Company",
            ticker_symbol="TST",
            exchange="NYSE",
            sector="Technology",
            industry="Software",
            isin="US1234567890",
            created_at=now,
            updated_at=now,
        ))

        mock_instance = mock_ticker.return_value
        import pandas as pd
        df = pd.DataFrame([{
            "Open": 140.0, "High": 145.0, "Low": 138.0, "Close": 142.0, "Volume": 500000
        }], index=[pd.Timestamp("2026-07-12")])
        mock_instance.history.return_value = df

        response = client.get(f"/api/v1/companies/{company_id}/history?range=1M")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["close"] == 142.0

