from fastapi import APIRouter
from app.schemas import Msg

router = APIRouter()


@router.get("", response_model=Msg)
async def list_events() -> Msg:
    """Placeholder list events endpoint."""
    return Msg(msg="List events route placeholder")


@router.get("/{event_id}", response_model=Msg)
async def get_event(event_id: str) -> Msg:
    """Placeholder get event endpoint."""
    return Msg(msg=f"Get event {event_id} route placeholder")
