import io
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from fastapi.testclient import TestClient
from app.models.document import Document, UploadStatus, ProcessingStatus, DocumentType
from app.services.document import DocumentService
from app.schemas.document import DocumentCreate


@pytest.fixture
def mock_storage():
    """Mock StorageService to prevent actual calls to MinIO."""
    with patch("app.services.document.StorageService") as MockStorage:
        instance = MockStorage.return_value
        instance.upload_file.return_value = "finiq-documents/test-path.pdf"
        instance.delete_file.return_value = None
        yield instance


@pytest.fixture
def mock_tasks():
    """Mock Celery process_document_task.delay."""
    with patch("app.services.document.process_document_task") as mock_task:
        mock_delay = MagicMock()
        mock_task.delay = mock_delay
        yield mock_delay


@pytest.mark.asyncio
async def test_document_service_upload_success(mock_storage, mock_tasks):
    """Verify DocumentService processes a valid upload, saves to MinIO and enqueues Celery task."""
    db_mock = AsyncMock()
    service = DocumentService(db_mock)
    service.storage = mock_storage

    company_id = uuid4()
    doc_id = uuid4()
    now = datetime.utcnow()

    # Mock repository methods
    service.repository = AsyncMock()
    service.repository.create.return_value = Document(
        id=doc_id,
        company_id=company_id,
        title="Annual Report 2026",
        document_type=DocumentType.annual_report,
        fiscal_year=2026,
        quarter=None,
        file_name="report.pdf",
        file_path=f"documents/{company_id}/{doc_id}.pdf",
        file_size=100,
        mime_type="application/pdf",
        upload_status=UploadStatus.pending,
        processing_status=ProcessingStatus.pending,
        uploaded_at=now,
        created_at=now,
        updated_at=now,
    )

    # Prepare mock file
    mock_file = AsyncMock()
    mock_file.filename = "report.pdf"
    mock_file.size = 100
    mock_file.read.return_value = b"mockpdfcontent"
    mock_file.content_type = "application/pdf"

    # Patch uuid4 to return our pre-defined doc_id
    with patch("uuid.uuid4", return_value=doc_id):
        result = await service.upload_document(
            company_id=company_id,
            title="Annual Report 2026",
            document_type=DocumentType.annual_report,
            fiscal_year=2026,
            quarter=None,
            file=mock_file,
        )

    # Asserts
    assert result.id == doc_id
    assert result.title == "Annual Report 2026"
    assert result.upload_status == UploadStatus.completed

    # Verify storage upload stream called
    mock_storage.upload_stream.assert_called_once()
    # Verify celery task queued
    mock_tasks.assert_called_once_with(str(doc_id))


@pytest.mark.asyncio
async def test_document_service_upload_invalid_extension():
    """Verify DocumentService rejects files with invalid extensions."""
    db_mock = AsyncMock()
    service = DocumentService(db_mock)

    mock_file = AsyncMock()
    mock_file.filename = "malicious.exe"
    mock_file.read.return_value = b"content"

    with pytest.raises(ValueError) as exc_info:
        await service.upload_document(
            company_id=uuid4(),
            title="Exploit",
            document_type=DocumentType.other,
            fiscal_year=2026,
            quarter=None,
            file=mock_file,
        )
    assert "Unsupported file type" in str(exc_info.value)


@pytest.mark.asyncio
async def test_document_service_upload_exceeds_size():
    """Verify DocumentService rejects files exceeding configured 200MB size limit."""
    db_mock = AsyncMock()
    service = DocumentService(db_mock)

    mock_file = AsyncMock()
    mock_file.filename = "too_large.pdf"
    mock_file.content_type = "application/pdf"
    mock_file.size = 201 * 1024 * 1024

    with pytest.raises(ValueError) as exc_info:
        await service.upload_document(
            company_id=uuid4(),
            title="Too Large File",
            document_type=DocumentType.other,
            fiscal_year=2026,
            quarter=None,
            file=mock_file,
        )
    assert "exceeds maximum limit" in str(exc_info.value)


@pytest.mark.asyncio
async def test_document_service_upload_valid_large_file():
    """Verify DocumentService accepts valid large file uploads (~150MB)."""
    db_mock = AsyncMock()
    service = DocumentService(db_mock)
    service.storage = MagicMock()

    import io
    mock_file = AsyncMock()
    mock_file.filename = "valid_150mb.pdf"
    mock_file.content_type = "application/pdf"
    
    # 150MB file size simulation
    valid_size = 150 * 1024 * 1024
    mock_file.size = valid_size
    fake_stream = io.BytesIO(b"header_data" + b"0" * 1024)
    underlying_file = MagicMock()
    underlying_file.tell.return_value = valid_size
    underlying_file.read.side_effect = lambda size=-1: fake_stream.read(size)
    mock_file.file = underlying_file

    # Mock DB calls
    service.repository.db.execute.return_value.scalars.return_value.first.return_value = None
    mock_doc = MagicMock()
    mock_doc.id = uuid4()
    mock_doc.mime_type = "application/pdf"
    service.repository.create = AsyncMock(return_value=mock_doc)

    with patch("app.services.document.process_document_task") as mock_task:
        result = await service.upload_document(
            company_id=uuid4(),
            title="Valid Large File",
            document_type=DocumentType.other,
            fiscal_year=2026,
            quarter=None,
            file=mock_file,
        )
        assert result is not None
        assert service.storage.upload_stream.called


def test_api_upload_document(client: TestClient):
    """Test the POST /documents endpoint."""
    company_id = uuid4()
    doc_id = uuid4()
    now = datetime.utcnow()

    with patch("app.api.v1.routers.document.DocumentService") as MockService:
        instance = MockService.return_value
        instance.upload_document = AsyncMock(return_value=Document(
            id=doc_id,
            company_id=company_id,
            title="Investor Presentation",
            document_type=DocumentType.investor_presentation,
            fiscal_year=2026,
            quarter=3,
            file_name="presentation.pptx",
            file_path=f"documents/{company_id}/{doc_id}.pptx",
            file_size=1024,
            mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            upload_status=UploadStatus.completed,
            processing_status=ProcessingStatus.pending,
            uploaded_at=now,
            created_at=now,
            updated_at=now,
        ))

        # Prepare payload and files for multipart/form-data
        payload = {
            "company_id": str(company_id),
            "title": "Investor Presentation",
            "document_type": "investor_presentation",
            "fiscal_year": "2026",
            "quarter": "3",
        }
        file_payload = {
            "file": ("presentation.pptx", io.BytesIO(b"presentationcontent"), "application/vnd.openxmlformats-officedocument.presentationml.presentation")
        }

        response = client.post("/api/v1/documents", data=payload, files=file_payload)
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Investor Presentation"
        assert data["upload_status"] == "completed"


def test_api_delete_document(client: TestClient):
    """Test the DELETE /documents/{id} endpoint."""
    doc_id = uuid4()
    company_id = uuid4()
    now = datetime.utcnow()

    with patch("app.api.v1.routers.document.DocumentService") as MockService:
        instance = MockService.return_value
        instance.delete_document = AsyncMock(return_value=Document(
            id=doc_id,
            company_id=company_id,
            title="Report to Delete",
            document_type=DocumentType.quarterly_report,
            fiscal_year=2026,
            quarter=2,
            file_name="delete.pdf",
            file_path=f"documents/{company_id}/{doc_id}.pdf",
            file_size=100,
            mime_type="application/pdf",
            upload_status=UploadStatus.completed,
            processing_status=ProcessingStatus.completed,
            uploaded_at=now,
            created_at=now,
            updated_at=now,
        ))

        response = client.delete(f"/api/v1/documents/{doc_id}")
        assert response.status_code == 200
        assert response.json()["id"] == str(doc_id)
