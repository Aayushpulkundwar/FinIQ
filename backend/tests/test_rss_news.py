import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import feedparser

from app.schemas.news import NewsArticle
from app.services.rss_news import fetch_company_news


def _create_mock_entry(title: str, link: str, days_ago: int = 1, summary: str = "Sample news excerpt", source_title: str = "Financial Express"):
    """Helper to construct feedparser FeedParserDict entries."""
    entry = feedparser.FeedParserDict()
    entry.title = title
    entry.link = link
    entry.summary = summary
    
    pub_dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    entry.published_parsed = pub_dt.timetuple()
    
    src = feedparser.FeedParserDict()
    src.title = source_title
    entry.source = src
    return entry


@pytest.mark.asyncio
async def test_fetch_company_news_merges_and_deduplicates_feeds():
    """Verify Google News and static feeds are fetched, parsed, deduplicated, and returned as NewsArticle list."""
    g_entry = _create_mock_entry(
        title="TVS Supply Chain signs strategic logistics agreement",
        link="https://news.google.com/articles/1",
        days_ago=1,
        source_title="Google News",
    )
    # Duplicate entry with slightly different casing/punctuation
    et_entry = _create_mock_entry(
        title="TVS Supply Chain signs strategic logistics agreement!",
        link="https://economictimes.com/news/1",
        days_ago=2,
        source_title="Economic Times",
    )
    # Distinct entry
    mc_entry = _create_mock_entry(
        title="TVS Supply Chain reports Q3 financial results",
        link="https://moneycontrol.com/news/2",
        days_ago=3,
        source_title="Moneycontrol",
    )

    mock_google_feed = feedparser.FeedParserDict()
    mock_google_feed.feed = feedparser.FeedParserDict({"title": "Google News"})
    mock_google_feed.entries = [g_entry]

    mock_et_feed = feedparser.FeedParserDict()
    mock_et_feed.feed = feedparser.FeedParserDict({"title": "Economic Times"})
    mock_et_feed.entries = [et_entry]

    mock_mc_feed = feedparser.FeedParserDict()
    mock_mc_feed.feed = feedparser.FeedParserDict({"title": "Moneycontrol"})
    mock_mc_feed.entries = [mc_entry]

    def mock_get_response(url, headers=None):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        if "google" in url:
            mock_resp.text = "google_xml"
        elif "economictimes" in url:
            mock_resp.text = "et_xml"
        else:
            mock_resp.text = "mc_xml"
        return mock_resp

    def mock_feedparser_parse(xml_str):
        if xml_str == "google_xml":
            return mock_google_feed
        elif xml_str == "et_xml":
            return mock_et_feed
        else:
            return mock_mc_feed

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=mock_get_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch("feedparser.parse", side_effect=mock_feedparser_parse):

        articles = await fetch_company_news(company_name="TVS Supply Chain Solutions Limited", ticker="TVSSCS", limit=10)

        # Output should be deduplicated (2 articles, not 3) and sorted descending by date
        assert len(articles) == 2
        assert isinstance(articles[0], NewsArticle)
        assert articles[0].title == "TVS Supply Chain signs strategic logistics agreement"
        assert articles[1].title == "TVS Supply Chain reports Q3 financial results"


@pytest.mark.asyncio
async def test_fetch_company_news_handles_broken_feed_gracefully():
    """Verify that one broken/unreachable feed does not crash the entire news fetch."""
    g_entry = _create_mock_entry(
        title="TVS Supply Chain expands warehousing capacity",
        link="https://news.google.com/articles/2",
        days_ago=1,
    )

    mock_google_feed = feedparser.FeedParserDict()
    mock_google_feed.feed = feedparser.FeedParserDict({"title": "Google News"})
    mock_google_feed.entries = [g_entry]

    async def mock_client_get(url, headers=None):
        if "google" in url:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "google_xml"
            return mock_resp
        else:
            raise Exception("Feed connection timed out")

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=mock_client_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch("feedparser.parse", return_value=mock_google_feed):

        articles = await fetch_company_news(company_name="TVS Supply Chain", limit=10)
        assert len(articles) == 1
        assert articles[0].title == "TVS Supply Chain expands warehousing capacity"


@pytest.mark.asyncio
async def test_fetch_company_news_filters_stale_articles():
    """Verify freshness_days parameter excludes articles older than freshness threshold."""
    fresh_entry = _create_mock_entry(
        title="Recent TVS announcement",
        link="https://news.google.com/articles/fresh",
        days_ago=5,
    )
    stale_entry = _create_mock_entry(
        title="Old TVS story from last month",
        link="https://news.google.com/articles/stale",
        days_ago=30,
    )

    mock_feed = feedparser.FeedParserDict()
    mock_feed.feed = feedparser.FeedParserDict({"title": "Google News"})
    mock_feed.entries = [fresh_entry, stale_entry]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "xml_content"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch("feedparser.parse", return_value=mock_feed):

        articles = await fetch_company_news(company_name="TVS", freshness_days=14, limit=10)
        assert len(articles) == 1
        assert articles[0].title == "Recent TVS announcement"


@pytest.mark.asyncio
async def test_fetch_company_news_empty_result_triggers_unavailable_message_downstream():
    """Verify empty feed results [] trigger 'Live news currently unavailable' message downstream without crashing."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("All feeds offline"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        articles = await fetch_company_news(company_name="Unknown Entity XYZ", limit=10)
        assert articles == []

    # Verify MarketIntelligenceService handles empty articles list gracefully
    from app.services.market_intelligence import MarketIntelligenceService
    mock_company_repo = AsyncMock()
    mock_company = MagicMock()
    mock_company.id = uuid4()
    mock_company.company_name = "Unknown Entity XYZ"
    mock_company.ticker_symbol = "XYZ"
    mock_company_repo.get = AsyncMock(return_value=mock_company)

    mock_db = AsyncMock()
    service = MarketIntelligenceService(mock_db)
    service.company_repo.get = AsyncMock(return_value=mock_company)

    with patch("app.services.rss_news.fetch_company_news", AsyncMock(return_value=[])):
        res = await service.analyze(company_id=mock_company.id)
        assert "Live news currently unavailable" in res.market_summary
