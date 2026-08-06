import hashlib
from datetime import datetime
from typing import List, Optional
import httpx
from fastapi import HTTPException, status
from loguru import logger

from app.core.config import settings
from app.schemas.news import NewsArticle


async def fetch_company_news(
    company_name: str,
    ticker: Optional[str] = None,
    limit: int = 20,
    topic_keywords: Optional[List[str]] = None,
) -> List[NewsArticle]:
    """
    Fetches real-time company news from APITube API filtering specifically by company entity
    and optional topic keywords.
    
    Raises:
        HTTPException 502: Invalid / missing APITube API key or 401/403 auth error.
        HTTPException 503: Timeout, rate limit (429), or 5xx server error from APITube.
    """
    api_key = settings.APITUBE_API_KEY
    if not api_key or "placeholder" in (api_key or "").lower():
        logger.error("APITube: APITUBE_API_KEY is missing or placeholder.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="APITube API key is invalid or missing. Please configure APITUBE_API_KEY."
        )

    base_url = settings.APITUBE_BASE_URL.rstrip("/")
    endpoint = f"{base_url}/v1/news/everything"
    
    # Clean company name for strict title matching (remove corporate entity suffixes)
    clean_company = company_name.strip()
    title_entity = (
        clean_company
        .replace(" Limited", "")
        .replace(" Ltd", "")
        .replace(" Corporation", "")
        .replace(" Corp", "")
        .replace(" Inc", "")
        .strip()
    )

    params = {
        "api_key": api_key,
        "title": title_entity,
        "per_page": min(limit, 50),
        "language.code": "en",
    }

    if topic_keywords and len(topic_keywords) > 0:
        formatted_terms = [f'"{k.strip()}"' if " " in k.strip() else k.strip() for k in topic_keywords if k.strip()]
        params["q"] = " OR ".join(formatted_terms)

    search_query = f"title='{title_entity}'" + (f" q='{params.get('q')}'" if "q" in params else "")

    headers = {
        "X-API-Key": api_key,
        "User-Agent": "FinIQ/1.0",
    }

    logger.info(f"APITube: Fetching news for '{company_name}' (query='{search_query}', limit={limit})")

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.get(endpoint, params=params, headers=headers)
            
            if resp.status_code in (401, 403):
                logger.error(f"APITube: Auth failed with HTTP {resp.status_code}: {resp.text}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"APITube authentication failed (HTTP {resp.status_code}). Check APITUBE_API_KEY."
                )

            if resp.status_code == 429:
                logger.warning("APITube: Rate limit exceeded (HTTP 429).")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="APITube rate limit exceeded. Please try again later."
                )

            if resp.status_code >= 500:
                logger.error(f"APITube: Server error HTTP {resp.status_code}: {resp.text}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"APITube news service error (HTTP {resp.status_code})."
                )

            if resp.status_code != 200:
                logger.error(f"APITube: Unexpected status {resp.status_code}: {resp.text}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"APITube news service returned unexpected status {resp.status_code}."
                )

            data = resp.json()

    except httpx.TimeoutException:
        logger.error("APITube: Request timed out after 10s.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="APITube news service request timed out."
        )
    except httpx.RequestError as exc:
        logger.error(f"APITube: Connection failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to connect to APITube news service: {exc}"
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"APITube: Unexpected error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"APITube news processing error: {exc}"
        )

    # Parse APITube JSON response
    raw_articles = (
        data.get("results") or
        data.get("data") or
        data.get("articles") or
        []
    )

    articles: List[NewsArticle] = []
    for idx, item in enumerate(raw_articles[:limit]):
        try:
            # APITube uses 'href' for the primary article URL
            url = item.get("href") or item.get("url") or item.get("link") or f"https://apitube.io/article/{idx}"
            title = item.get("title") or item.get("headline") or "Untitled News Article"
            snippet = item.get("snippet") or item.get("description") or item.get("summary")
            
            # Source resolution
            source_raw = item.get("source")
            if isinstance(source_raw, dict):
                source_name = source_raw.get("name") or source_raw.get("domain") or "APITube News"
            elif isinstance(source_raw, str):
                source_name = source_raw
            else:
                source_name = item.get("publisher") or "Financial News"

            # Image URL resolution
            image_url = item.get("image_url") or item.get("image") or item.get("thumbnail")
            if isinstance(image_url, dict):
                image_url = image_url.get("url")

            # Timestamp resolution
            pub_date_raw = item.get("published_at") or item.get("pub_date") or item.get("date")
            published_at = datetime.utcnow()
            if pub_date_raw:
                try:
                    published_at = datetime.fromisoformat(str(pub_date_raw).replace("Z", "+00:00"))
                except Exception:
                    pass

            article_id = item.get("id") or hashlib.md5(f"{url}:{title}".encode("utf-8")).hexdigest()

            articles.append(
                NewsArticle(
                    id=str(article_id),
                    title=title,
                    snippet=snippet,
                    source=source_name,
                    url=url,
                    image_url=image_url if isinstance(image_url, str) else None,
                    published_at=published_at,
                )
            )
        except Exception as parse_err:
            logger.warning(f"APITube: Skipping article parse error: {parse_err}")

    logger.info(f"APITube: Successfully parsed {len(articles)} articles for '{company_name}'.")
    return articles
