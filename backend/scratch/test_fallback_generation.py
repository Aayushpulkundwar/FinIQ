import asyncio
from app.services.response_generation import ResponseGenerationService
from app.services.rss_news import fetch_company_news

async def main():
    company_name = "TVS Supply Chain Solutions Limited"
    ticker = "TVSSCS"
    user_query = "What's the latest news on TVS Supply Chain?"
    
    print(f"Fetching RSS news for '{company_name}'...")
    articles = fetch_company_news(company_name=company_name, ticker=ticker)
    print(f"Retrieved {len(articles)} RSS articles.")
    
    retrieved_chunks = [
        {
            "chunk_text": a.snippet or a.title,
            "document_title": a.source or "Web News",
            "page_number": None,
            "published_at": a.published_at.isoformat(),
            "url": a.url,
        }
        for a in articles
    ]
    
    gen_svc = ResponseGenerationService()
    ai_resp = await gen_svc._generate_fallback(
        user_query=user_query,
        company_details={"company_name": company_name, "ticker_symbol": ticker},
        retrieved_chunks=retrieved_chunks,
        cache_key="test_fallback_key",
    )
    
    print("\n=======================================================")
    print(f"EXECUTIVE SUMMARY:\n{ai_resp.executive_summary}")
    print(f"KEY INSIGHTS:\n{ai_resp.key_insights}")
    print(f"SOURCES:\n{ai_resp.sources}")
    print(f"SUPPORTING EVIDENCE:\n{ai_resp.supporting_evidence}")
    print(f"GENERATION MODE: {ai_resp.generation_mode}")

if __name__ == "__main__":
    asyncio.run(main())
