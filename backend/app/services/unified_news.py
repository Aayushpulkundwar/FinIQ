from typing import List, Optional
from loguru import logger
from app.core.config import settings
from app.schemas.news import NewsArticle
from app.services.rss_news import fetch_company_news as rss_fetch


def is_valid_apitube_key(api_key: Optional[str]) -> bool:
    if not api_key or not isinstance(api_key, str):
        return False
    key_lower = api_key.strip().lower()
    invalid_patterns = ["placeholder", "your_", "your-", "your_production", "api_key_here", "example"]
    if any(pattern in key_lower for pattern in invalid_patterns):
        return False
    return len(key_lower) > 10


async def fetch_harmonized_company_news(
    company_name: str,
    ticker: Optional[str] = None,
    limit: int = 20,
    topic_keywords: Optional[List[str]] = None,
) -> List[NewsArticle]:
    """
    Unified news fetcher for FinIQ:
    Tries APITube first ONLY if APITUBE_API_KEY is present and not a placeholder/template string.
    If APITube is unconfigured or fails, seamlessly falls back to RSS News (Google News + Indian Financial RSS).
    """
    api_key = getattr(settings, "APITUBE_API_KEY", None)
    if is_valid_apitube_key(api_key):
        try:
            from app.services.apitube_news import fetch_company_news as apitube_fetch
            articles = await apitube_fetch(company_name, ticker, limit, topic_keywords)
            if articles:
                return articles
            logger.info(f"APITube returned 0 articles for '{company_name}', falling back to RSS news.")
        except Exception as err:
            logger.warning(f"APITube news fetch failed for '{company_name}' ({err}), falling back to RSS news.")

    return await rss_fetch(company_name, ticker, limit=limit)
