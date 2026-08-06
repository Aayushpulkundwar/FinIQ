import asyncio
from app.services.rss_news import fetch_company_news
from app.services.market_intelligence import MarketIntelligenceService
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

async def test_news_query(company_name: str, ticker: str):
    print(f"\n=======================================================")
    print(f"TESTING NEWS FETCH FOR: '{company_name}' ({ticker})")
    print(f"=======================================================")
    articles = await fetch_company_news(company_name=company_name, ticker=ticker)
    print(f"\nRESULT: Sourced {len(articles)} articles.")
    for i, a in enumerate(articles, 1):
        print(f" Article #{i}: [{a.source}] ({a.published_at.strftime('%Y-%m-%d')}) {a.title}\n   Link: {a.url}")

async def main():
    await test_news_query("TVS Supply Chain Solutions Limited", "TVSSCS")
    await test_news_query("Reliance Industries Limited", "RELIANCE")
    await test_news_query("Tata Motors Limited", "TATAMOTORS")

if __name__ == "__main__":
    asyncio.run(main())
