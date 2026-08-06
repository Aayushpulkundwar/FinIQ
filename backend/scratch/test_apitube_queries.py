import httpx
import json
from app.core.config import settings

def test_queries():
    api_key = settings.APITUBE_API_KEY
    url = "https://api.apitube.io/v1/news/everything"

    queries = [
        '"TVS Supply Chain Solutions Limited"',
        '"TVS Supply Chain"',
        'TVSSCS',
        '"TVS Supply Chain Solutions"',
        'TVS Supply Chain',
    ]

    for q in queries:
        print(f"=== TESTING QUERY: {q} ===")
        params = {"api_key": api_key, "q": q, "per_page": 5, "language.code": "en"}
        try:
            resp = httpx.get(url, params=params, timeout=10.0)
            print("Status:", resp.status_code)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                print(f"Count: {len(results)}")
                for idx, art in enumerate(results, 1):
                    src = art.get("source")
                    domain = src.get("domain") if isinstance(src, dict) else src
                    print(f"{idx}. [{domain}] {art.get('title')}")
                    print(f"   URL: {art.get('href')}")
            else:
                print("Error:", resp.text)
        except Exception as e:
            print("Exception:", e)
        print()

if __name__ == "__main__":
    test_queries()
