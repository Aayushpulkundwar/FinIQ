import asyncio
import json
from uuid import UUID
from app.db.session import SessionLocal
from app.api.v1.routers.company import get_company_financial_summary
from app.core.cache import cache
from app.services.financial_ratios_scraper import fetch_financial_ratios

TVSSCS_ID = UUID("3ec17afd-e43d-4cdc-8edb-89eed257d305")
VRLLOG_ID = UUID("8d24f866-be84-4193-84f3-d2f9a5b70948")

async def verify_ratios():
    async with SessionLocal() as db:
        print("==================================================")
        print("1. CLEARING RATIOS CACHE & VERIFYING TVSSCS FRESH FETCH")
        print("==================================================")
        await cache.invalidate_pattern(f"ratios:{TVSSCS_ID}")
        await cache.invalidate_pattern(f"ratios:{VRLLOG_ID}")

        tvsscs_res = await get_company_financial_summary(TVSSCS_ID, db)
        tvsscs_dict = tvsscs_res.model_dump()
        print("TVSSCS Fresh Endpoint Response:")
        print(json.dumps(tvsscs_dict, indent=2))

        assert tvsscs_dict["available"] is True
        assert tvsscs_dict["currency"] == "INR"
        assert tvsscs_dict["roe_source"] == "ratio_scraper"
        assert 5.0 <= tvsscs_dict["roe"] <= 10.0, f"TVSSCS ROE should be ~6.0%, got {tvsscs_dict['roe']}"
        print(f"PASS: TVSSCS ROE displays as {tvsscs_dict['roe']}% (sourced via ratio_scraper)")

        print("\n==================================================")
        print("2. VERIFYING VRLLOG FRESH FETCH")
        print("==================================================")
        vrllog_res = await get_company_financial_summary(VRLLOG_ID, db)
        vrllog_dict = vrllog_res.model_dump()
        print("VRLLOG Fresh Endpoint Response:")
        print(json.dumps(vrllog_dict, indent=2))

        assert vrllog_dict["available"] is True
        assert vrllog_dict["currency"] == "INR"
        assert vrllog_dict["roe_source"] == "ratio_scraper"
        assert 15.0 <= vrllog_dict["roe"] <= 25.0, f"VRLLOG ROE should be ~21.27%, got {vrllog_dict['roe']}"
        print(f"PASS: VRLLOG ROE displays as {vrllog_dict['roe']}% (sourced via ratio_scraper)")

        print("\n==================================================")
        print("3. VERIFYING MSFT DIRECT SCRAPER FETCH")
        print("==================================================")
        msft_ratios = await fetch_financial_ratios("MSFT", "NASDAQ")
        msft_dict = msft_ratios.model_dump()
        print("MSFT Scraper Response:")
        print(json.dumps(msft_dict, indent=2))

        assert msft_dict["available"] is True
        assert msft_dict["currency"] == "USD"
        assert 30.0 <= msft_dict["roe_percent"] <= 40.0, f"MSFT ROE should be ~34%, got {msft_dict['roe_percent']}"
        print(f"PASS: MSFT ROE displays as {msft_dict['roe_percent']}% (sourced via ratio_scraper)")

        print("\n==================================================")
        print("ALL VERIFICATIONS PASSED PERFECTLY!")
        print("==================================================")

if __name__ == "__main__":
    asyncio.run(verify_ratios())
