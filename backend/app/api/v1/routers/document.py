from typing import List, Optional
from uuid import UUID
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.document import DocumentType
from app.schemas.document import Document
from app.services.document import DocumentService

router = APIRouter()


@router.post("", response_model=Document, status_code=status.HTTP_201_CREATED)
async def upload_document(
    company_id: UUID = Form(...),
    title: str = Form(...),
    document_type: DocumentType = Form(...),
    fiscal_year: int = Form(...),
    quarter: Optional[int] = Form(None),
    allow_supersede: bool = Form(False),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> Document:
    """
    Ingest a document file (PDF, DOCX, or PPTX) and store its metadata.
    Enqueues background verification/processing via Celery.
    """
    service = DocumentService(db)
    try:
        return await service.upload_document(
            company_id=company_id,
            title=title,
            document_type=document_type,
            fiscal_year=fiscal_year,
            quarter=quarter,
            file=file,
            allow_supersede=allow_supersede,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during file upload ingestion: {e}",
        )


@router.get("", response_model=List[Document])
async def list_documents(
    skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
) -> List[Document]:
    """
    Retrieve list of document metadata entries with optional pagination.
    """
    service = DocumentService(db)
    return await service.list_documents(skip=skip, limit=limit)


@router.get("/stalled", response_model=List[Document])
async def get_stalled_documents(
    threshold_minutes: int = 15, db: AsyncSession = Depends(get_db)
) -> List[Document]:
    """
    Returns document entries stuck in 'processing' status past the specified threshold.
    Uses dedicated heartbeat_at column.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from app.models.document import Document as DocModel, ProcessingStatus

    cutoff = datetime.utcnow() - timedelta(minutes=threshold_minutes)
    stmt = select(DocModel).where(
        DocModel.processing_status == ProcessingStatus.processing,
        DocModel.heartbeat_at <= cutoff
    )
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/stalled/count")
async def count_stalled_documents(
    threshold_minutes: int = 15, db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Lightweight diagnostic summary endpoint returning stuck document count for polling/monitoring.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import select, func
    from app.models.document import Document as DocModel, ProcessingStatus

    cutoff = datetime.utcnow() - timedelta(minutes=threshold_minutes)
    stmt = select(func.count(DocModel.id)).where(
        DocModel.processing_status == ProcessingStatus.processing,
        DocModel.heartbeat_at <= cutoff
    )
    res = await db.execute(stmt)
    stuck_count = res.scalar() or 0

    return {
        "stalled_count": stuck_count,
        "threshold_minutes": threshold_minutes,
        "checked_at": datetime.utcnow().isoformat()
    }


@router.get("/{id}", response_model=Document)
async def get_document(
    id: UUID, db: AsyncSession = Depends(get_db)
) -> Document:
    """
    Retrieve detailed document metadata by its UUID.
    """
    service = DocumentService(db)
    try:
        return await service.get_document(id)
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


@router.delete("/{id}", response_model=Document)
async def delete_document(
    id: UUID, db: AsyncSession = Depends(get_db)
) -> Document:
    """
    Deletes document metadata from database and deletes its file from MinIO.
    """
    service = DocumentService(db)
    try:
        return await service.delete_document(id)
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )
