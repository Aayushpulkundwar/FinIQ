import httpx
import json
import sys
from app.core.config import settings

def test_title_param():
    api_key = settings.APITUBE_API_KEY
    url = "https://api.apitube.io/v1/news/everything"

    queries = [
        "TVS Supply Chain",
        "TVS",
        "TVS Supply",
        "Logistics",
        "VRL Logistics",
        "VRL",
    ]

    for q in queries:
        print(f"=== TESTING TITLE PARAM: '{q}' ===", flush=True)
        params = {"api_key": api_key, "title": q, "per_page": 10, "language.code": "en"}
        try:
            resp = httpx.get(url, params=params, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                print(f"Count: {len(results)}", flush=True)
                for idx, art in enumerate(results, 1):
                    src = art.get("source")
                    domain = src.get("domain") if isinstance(src, dict) else src
                    # Clean Unicode chars for Windows console
                    title = str(art.get("title")).encode("ascii", "replace").decode("ascii")
                    print(f"  {idx}. [{domain}] {title}", flush=True)
                    print(f"     URL: {art.get('href')}", flush=True)
            else:
                print(f"  Status: {resp.status_code} {resp.text[:100]}", flush=True)
        except Exception as e:
            print("  Exception:", e, flush=True)
        print(flush=True)

if __name__ == "__main__":
    test_title_param()
