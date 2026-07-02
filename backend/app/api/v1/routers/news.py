from fastapi import APIRouter
from app.schemas import Msg

router = APIRouter()


@router.get("", response_model=Msg)
async def list_news() -> Msg:
    """Placeholder list news articles endpoint."""
    return Msg(msg="List news articles route placeholder")


@router.get("/{article_id}", response_model=Msg)
async def get_news_article(article_id: str) -> Msg:
    """Placeholder get news article endpoint."""
    return Msg(msg=f"Get news article {article_id} route placeholder")
