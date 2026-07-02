from fastapi import APIRouter
from app.schemas import Msg

router = APIRouter()


@router.post("/sessions", response_model=Msg)
async def create_chat_session() -> Msg:
    """Placeholder create chat session endpoint."""
    return Msg(msg="Create chat session route placeholder")


@router.post("/sessions/{session_id}/messages", response_model=Msg)
async def send_message(session_id: str) -> Msg:
    """Placeholder send message to session endpoint."""
    return Msg(msg=f"Send message to session {session_id} route placeholder")
