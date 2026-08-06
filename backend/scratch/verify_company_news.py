"""
[THROWAWAY SCRATCH SCRIPT]
This script is a standalone local diagnostic utility for quick manual testing.
It is NOT imported or reachable by any deployable application code path in FinIQ.
Do not use or import in production.
"""
import asyncio
import httpx
from loguru import logger
from app.core.config import settings

COMPANY_ID = "3ec17afd-e43d-4cdc-8edb-89eed257d305"  # TVS Supply Chain Solutions Limited
BASE_URL = "http://localhost:8000/api/v1"

async def test_endpoint(label: str):
    logger.info(f"\n=== TESTING: {label} ===")
    logger.info(f"APITUBE_API_KEY: '{settings.APITUBE_API_KEY}'")
    
    url = f"{BASE_URL}/companies/{COMPANY_ID}/news?limit=20"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        logger.info(f"HTTP Status: {resp.status_code}")
        try:
            data = resp.json()
            if resp.status_code == 200:
                logger.info(f"Company: {data.get('company_name')} ({data.get('ticker_symbol')})")
                logger.info(f"Article Count: {len(data.get('articles', []))}")
                if data.get('articles'):
                    first = data['articles'][0]
                    logger.info(f"Sample Article 1: '{first.get('title')}' [{first.get('source')}]")
            else:
                logger.info(f"Error Detail: {data.get('detail')}")
            return resp.status_code, data
        except Exception as e:
            logger.error(f"Response text: {resp.text}")
            return resp.status_code, resp.text

async def main():
    # 1. Deliberately break APITube access (invalid key)
    original_key = settings.APITUBE_API_KEY
    settings.APITUBE_API_KEY = "placeholder_invalid_key"
    
    status_broken, data_broken = await test_endpoint("1. BROKEN APITUBE KEY (Expect 502 Bad Gateway)")
    assert status_broken in (502, 503), f"Expected 502 or 503, got {status_broken}"
    print(f"[PASS] TEST 1: Broken key returned HTTP {status_broken} with detail: '{data_broken.get('detail')}'")

    # Restore key
    settings.APITUBE_API_KEY = original_key

    # 2. Test direct cache set and cache hit
    from app.core.cache import cache
    cache_key = f"news:{COMPANY_ID}"
    mock_payload = {
        "company_id": COMPANY_ID,
        "company_name": "TVS Supply Chain Solutions Limited",
        "ticker_symbol": "TVSSCS",
        "articles": [
            {
                "id": "art-101",
                "title": "TVS Supply Chain expands logistics operations in APAC",
                "snippet": "TVS Supply Chain Solutions announced a major expansion of its warehousing facilities across Southeast Asia.",
                "source": "Financial Express",
                "url": "https://example.com/tvs-apac-expansion",
                "image_url": "https://example.com/images/tvs.jpg",
                "published_at": "2026-07-28T10:00:00Z"
            },
            {
                "id": "art-102",
                "title": "TVS Supply Chain reports 18% YoY contract win growth",
                "snippet": "Strong momentum in automotive and industrial verticals drove contract renewals.",
                "source": "Economic Times",
                "url": "https://example.com/tvs-contract-wins",
                "image_url": None,
                "published_at": "2026-07-28T08:30:00Z"
            }
        ]
    }
    await cache.set(cache_key, mock_payload, ttl=900)

    # 3. Test Redis Cache Hit
    status_cached, data_cached = await test_endpoint("2. REDIS CACHE HIT (Expect 200 OK with cached articles)")
    assert status_cached == 200, f"Expected 200 OK, got {status_cached}"
    assert len(data_cached.get("articles", [])) == 2, "Expected 2 cached articles"
    print(f"[PASS] TEST 2: Cache hit returned HTTP 200 with {len(data_cached['articles'])} articles!")
    print(f"Article 1 Title: {data_cached['articles'][0]['title']}")


if __name__ == "__main__":
    asyncio.run(main())
