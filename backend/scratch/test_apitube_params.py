import httpx
import json
from app.core.config import settings

def test_apitube_params():
    api_key = settings.APITUBE_API_KEY
    url = "https://api.apitube.io/v1/news/everything"

    param_tests = [
        {"q": "TVS"},
        {"q": "Microsoft"},
        {"q": "Tesla"},
        {"q": "title:TVS"},
        {"title": "TVS"},
        {"q_in_title": "TVS"},
        {"q.in_title": "TVS"},
        {"q.in.title": "TVS"},
        {"search": "TVS"},
        {"query": "TVS"},
        {"keywords": "TVS"},
    ]

    for p in param_tests:
        print(f"=== TESTING PARAMS: {p} ===")
        params = {"api_key": api_key, "per_page": 3, "language.code": "en"}
        params.update(p)
        try:
            resp = httpx.get(url, params=params, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                print(f"Count: {len(results)}")
                for idx, art in enumerate(results[:3], 1):
                    src = art.get("source")
                    domain = src.get("domain") if isinstance(src, dict) else src
                    print(f"  {idx}. [{domain}] {art.get('title')}")
            else:
                print("  Status:", resp.status_code, resp.text[:100])
        except Exception as e:
            print("  Exception:", e)
        print()

if __name__ == "__main__":
    test_apitube_params()
