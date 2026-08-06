import hashlib
import re
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import quote, urlparse

import feedparser
import httpx
from loguru import logger

from app.core.config import settings
from app.schemas.news import NewsArticle


def _clean_company_name(name: str) -> str:
    """Removes corporate entity suffixes for clean query and feed matching."""
    clean = name.strip()
    for suffix in [
        " Limited", " Ltd", " Corporation", " Corp",
        " Inc", " Private", " Pvt", " (India)", " India"
    ]:
        if clean.endswith(suffix):
            clean = clean[:-len(suffix)].strip()
    return clean or name.strip()


def _clean_text(html_text: Optional[str]) -> str:
    """Strips HTML tags and unescapes basic HTML entities."""
    if not html_text:
        return ""
    text = re.sub(r"<[^>]+>", "", html_text)
    text = (
        text.replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    return re.sub(r"\s+", " ", text).strip()


def _parse_entry_date(entry: feedparser.FeedParserDict) -> datetime:
    """Extracts published timestamp as a UTC datetime."""
    published_parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if published_parsed:
        try:
            return datetime.fromtimestamp(time.mktime(published_parsed), tz=timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)


def _extract_source_name(entry: feedparser.FeedParserDict, feed_title: str, feed_url: str) -> str:
    """Extracts publisher/source name from RSS entry or feed metadata."""
    if hasattr(entry, "source") and hasattr(entry.source, "title") and entry.source.title:
        return entry.source.title.strip()
    if feed_title and "google" not in feed_title.lower():
        return feed_title.strip()
    # Fallback to domain name from URL
    link = getattr(entry, "link", "") or feed_url
    domain = urlparse(link).netloc.replace("www.", "")
    return domain.capitalize() if domain else "Financial Press"


def _normalize_title(title: str) -> str:
    """Normalized title string for deduplication."""
    return re.sub(r"[\W_]+", "", title.lower())


def _build_search_query(company_name: str, ticker: Optional[str] = None) -> str:
    """Constructs a high-precision, disambiguated search query for corporate news."""
    clean_company = _clean_company_name(company_name)
    clean_ticker = (ticker or "").split(".")[0].strip()

    is_ambiguous = len(clean_company.split()) == 1 or len(clean_company) <= 7

    if is_ambiguous:
        terms = [f'"{company_name}"']
        if clean_ticker and len(clean_ticker) >= 3:
            terms.append(f'"{clean_ticker} share price"')
            terms.append(f'"{clean_ticker} stock"')
        terms.append(f'"{clean_company} Ltd"')
        terms.append(f'"{clean_company} Limited"')
        return " OR ".join(terms)

    return f'"{company_name}" OR "{clean_company}"'


async def fetch_company_news(
    company_name: str,
    ticker: Optional[str] = None,
    freshness_days: Optional[int] = None,
    limit: Optional[int] = None,
) -> List[NewsArticle]:
    """
    Fetches real-time company news by combining Google News RSS and static Indian financial press RSS feeds.
    Merges, deduplicates, and sorts articles by publication date.
    
    Returns an empty list [] if all feeds fail or no matching articles are found.
    """
    days = freshness_days if freshness_days is not None else settings.RSS_NEWS_FRESHNESS_DAYS
    max_results = limit if limit is not None else settings.RSS_NEWS_MAX_RESULTS

    clean_company = _clean_company_name(company_name)
    clean_ticker = (ticker or "").split(".")[0].strip().lower()
    search_q = _build_search_query(company_name, ticker)

    logger.info(
        f"RSSNews: Starting fetch for '{company_name}' (query='{search_q}', "
        f"ticker='{clean_ticker}', freshness_days={days}, max_results={max_results})"
    )

    # Build target RSS feed URLs
    google_rss_url = f"https://news.google.com/rss/search?q={quote(search_q)}&hl=en-IN&gl=IN&ceid=IN:en"
    feed_urls = [google_rss_url] + (settings.RSS_FEED_URLS or [])

    raw_entries: List[dict] = []
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    headers = {"User-Agent": "FinIQ/1.0 (Financial Intelligence Platform)"}

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for url in feed_urls:
            is_google = "news.google.com" in url
            logger.info(f"RSSNews: Fetching feed URL: {url}")
            try:
                # Fetch feed content with httpx
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    logger.warning(f"RSSNews: Feed {url} returned HTTP {resp.status_code}")
                    continue

                parsed = feedparser.parse(resp.text)
                feed_title = getattr(parsed.feed, "title", "")
                entries = getattr(parsed, "entries", []) or []

                raw_count = len(entries)
                company_matched_count = 0
                fresh_count = 0

                for entry in entries:
                    title = _clean_text(getattr(entry, "title", ""))
                    if not title:
                        continue

                    snippet = _clean_text(getattr(entry, "summary", "") or getattr(entry, "description", ""))
                    link = getattr(entry, "link", "") or getattr(entry, "id", "")

                    # For static (non-Google) feeds, filter items matching company_name or ticker
                    if not is_google:
                        title_desc = (title + " " + snippet).lower()
                        full_name_match = clean_company.lower() in title_desc
                        ticker_match = len(clean_ticker) >= 3 and clean_ticker in title_desc
                        brand_word = clean_company.split()[0].lower()
                        brand_match = len(brand_word) >= 3 and brand_word in title_desc
                        if not (full_name_match or ticker_match or brand_match):
                            continue

                    company_matched_count += 1

                    pub_dt = _parse_entry_date(entry)
                    if pub_dt < cutoff_date:
                        continue

                    fresh_count += 1
                    source_name = _extract_source_name(entry, feed_title, url)

                    # Unique ID generation from URL / title hash
                    art_id = hashlib.sha256(f"{link}-{title}".encode("utf-8")).hexdigest()[:16]

                    raw_entries.append({
                        "id": art_id,
                        "title": title,
                        "snippet": snippet[:300] if snippet else title,
                        "source": source_name,
                        "url": link,
                        "published_at": pub_dt,
                        "norm_title": _normalize_title(title),
                    })

                logger.info(
                    f"RSSNews: Feed '{url[:60]}' -> {raw_count} raw entries | "
                    f"{company_matched_count} company-matched | "
                    f"{fresh_count} fresh (>= {cutoff_date.strftime('%Y-%m-%d')})"
                )

            except Exception as feed_err:
                logger.warning(f"RSSNews: Feed {url} fetch/parse failed: {feed_err}")
                continue

    # Deduplicate entries by URL and fuzzy title match
    seen_urls = set()
    seen_titles = set()
    deduped_entries = []

    for item in raw_entries:
        link = item["url"]
        norm_title = item["norm_title"]

        if link in seen_urls or norm_title in seen_titles:
            continue

        seen_urls.add(link)
        seen_titles.add(norm_title)
        deduped_entries.append(item)

    # Sort descending by published_at
    deduped_entries.sort(key=lambda x: x["published_at"], reverse=True)

    # Convert to NewsArticle Pydantic models
    articles = [
        NewsArticle(
            id=item["id"],
            title=item["title"],
            snippet=item["snippet"],
            source=item["source"],
            url=item["url"],
            published_at=item["published_at"],
        )
        for item in deduped_entries[:max_results]
    ]

    logger.info(
        f"RSSNews: Sourced {len(raw_entries)} candidate items before dedup. "
        f"Final deduped & sorted count: {len(articles)} for '{company_name}'."
    )
    return articles
