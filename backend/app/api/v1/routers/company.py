from fastapi import APIRouter
from app.schemas import Msg

router = APIRouter()


@router.get("", response_model=Msg)
async def list_companies() -> Msg:
    """Placeholder list companies endpoint."""
    return Msg(msg="List companies route placeholder")


@router.get("/{company_id}", response_model=Msg)
async def get_company(company_id: str) -> Msg:
    """Placeholder get company by ID endpoint."""
    return Msg(msg=f"Get company {company_id} route placeholder")
