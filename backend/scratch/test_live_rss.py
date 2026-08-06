import asyncio
from app.services.rss_news import fetch_company_news

async def main():
    print("Testing live RSS news fetch for 'TVS Supply Chain Solutions Limited'...")
    articles = await fetch_company_news("TVS Supply Chain Solutions Limited", ticker="TVSSCS")
    print(f"Retrieved {len(articles)} articles:")
    for a in articles:
        print(f"- [{a.source}] ({a.published_at.strftime('%Y-%m-%d')}) {a.title}\n  URL: {a.url}\n")

if __name__ == "__main__":
    asyncio.run(main())
