from fastapi import APIRouter, Depends, status
from app.schemas import Msg

router = APIRouter()


@router.post("/login", response_model=Msg)
async def login() -> Msg:
    """Placeholder login endpoint."""
    return Msg(msg="Login route placeholder")


@router.post("/register", response_model=Msg, status_code=status.HTTP_201_CREATED)
async def register() -> Msg:
    """Placeholder registration endpoint."""
    return Msg(msg="Register route placeholder")
