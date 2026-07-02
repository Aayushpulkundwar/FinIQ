from fastapi import APIRouter
from app.schemas import Msg

router = APIRouter()


@router.post("/upload", response_model=Msg)
async def upload_document() -> Msg:
    """Placeholder upload document endpoint."""
    return Msg(msg="Upload document route placeholder")


@router.get("", response_model=Msg)
async def list_documents() -> Msg:
    """Placeholder list documents endpoint."""
    return Msg(msg="List documents route placeholder")
