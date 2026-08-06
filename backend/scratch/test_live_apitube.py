import httpx
import json
from app.core.config import settings

def test_raw_apitube(api_key: str, query: str = '"TVS Supply Chain"'):
    url = "https://api.apitube.io/v1/news/everything"
    params = {
        "api_key": api_key,
        "q": query,
        "per_page": 5,
        "language.code": "en"
    }
    headers = {
        "X-API-Key": api_key,
        "User-Agent": "FinIQ/1.0"
    }
    
    resp = httpx.get(url, params=params, headers=headers, timeout=10.0)
    print("STATUS:", resp.status_code)
    data = resp.json()
    results = data.get("results", [])
    print(f"\nFetched {len(results)} live articles for query '{query}':\n")
    for idx, art in enumerate(results[:3], 1):
        print(f"--- Article {idx} ---")
        print("Title:", art.get("title"))
        source_domain = art.get("source", {}).get("domain") if isinstance(art.get("source"), dict) else "APITube"
        print("Source Domain:", source_domain)
        print("URL (href):", art.get("href"))
        print("Published At:", art.get("published_at"))
        print()

if __name__ == "__main__":
    key = settings.APITUBE_API_KEY or ""
    test_raw_apitube(key)
