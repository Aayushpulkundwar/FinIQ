import httpx
import json
from app.core.config import settings

def test_title_and_q():
    api_key = settings.APITUBE_API_KEY
    url = "https://api.apitube.io/v1/news/everything"

    params = {
        "api_key": api_key,
        "title": "TVS Supply Chain",
        "q": "aerospace OR defence OR growth",
        "per_page": 5,
        "language.code": "en"
    }

    resp = httpx.get(url, params=params, timeout=10.0)
    print("Status:", resp.status_code)
    if resp.status_code == 200:
        results = resp.json().get("results", [])
        print("Count:", len(results))
        for idx, art in enumerate(results, 1):
            src = art.get("source")
            domain = src.get("domain") if isinstance(src, dict) else src
            title = str(art.get("title")).encode("ascii", "replace").decode("ascii")
            print(f"{idx}. [{domain}] {title}")
            print(f"   URL: {art.get('href')}")

if __name__ == "__main__":
    test_title_and_q()
