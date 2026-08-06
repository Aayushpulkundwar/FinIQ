import asyncio
import json
from uuid import UUID
from app.db.session import SessionLocal
from app.api.v1.routers.company import get_company_financial_summary

TVSSCS_ID = UUID("3ec17afd-e43d-4cdc-8edb-89eed257d305")
VRLLOG_ID = UUID("8d24f866-be84-4193-84f3-d2f9a5b70948")

def simulate_frontend_format_market_cap(val, currency):
    if val is None:
        return "—"
    if currency == "INR":
        crore = val / 1e7
        if crore >= 100000:
            return f"Rs. {(crore / 100000):,.2f} L Cr"
        return f"Rs. {round(crore):,} Cr"
    else:
        abs_v = abs(val)
        if abs_v >= 1e12:
            return f"${abs_v/1e12:.2f}T"
        if abs_v >= 1e9:
            return f"${abs_v/1e9:.2f}B"
        if abs_v >= 1e6:
            return f"${abs_v/1e6:.2f}M"
        return f"${abs_v:,}"

def simulate_frontend_format_percent(val):
    if val is None:
        return "—"
    percent_val = val * 100 if abs(val) < 1.0 else val
    return f"{percent_val:.2f}%"

async def verify_fixes():
    async with SessionLocal() as db:
        print("==================================================")
        print("1. VERIFYING TVSSCS FINANCIAL SUMMARY ENDPOINT")
        print("==================================================")
        tvsscs_res = await get_company_financial_summary(TVSSCS_ID, db)
        tvsscs_dict = tvsscs_res.model_dump()
        print("TVSSCS Raw Endpoint Response:")
        print(json.dumps(tvsscs_dict, indent=2))

        print("\nTVSSCS Frontend Formatted Values:")
        print(f"  Revenue:     {simulate_frontend_format_market_cap(tvsscs_dict['revenue'], tvsscs_dict['currency'])}")
        print(f"  EBITDA:      {simulate_frontend_format_market_cap(tvsscs_dict['ebitda'], tvsscs_dict['currency'])}")
        print(f"  Net Profit:  {simulate_frontend_format_market_cap(tvsscs_dict['net_profit'], tvsscs_dict['currency'])}")
        print(f"  ROE:         {simulate_frontend_format_percent(tvsscs_dict['roe'])}")

        print("\n==================================================")
        print("2. VERIFYING VRLLOG FINANCIAL SUMMARY ENDPOINT")
        print("==================================================")
        vrllog_res = await get_company_financial_summary(VRLLOG_ID, db)
        vrllog_dict = vrllog_res.model_dump()
        print("VRLLOG Raw Endpoint Response:")
        print(json.dumps(vrllog_dict, indent=2))

        print("\nVRLLOG Frontend Formatted Values:")
        print(f"  Revenue:     {simulate_frontend_format_market_cap(vrllog_dict['revenue'], vrllog_dict['currency'])}")
        print(f"  EBITDA:      {simulate_frontend_format_market_cap(vrllog_dict['ebitda'], vrllog_dict['currency'])}")
        print(f"  Net Profit:  {simulate_frontend_format_market_cap(vrllog_dict['net_profit'], vrllog_dict['currency'])}")
        print(f"  ROE:         {simulate_frontend_format_percent(vrllog_dict['roe'])}")

        assert tvsscs_dict["currency"] == "INR", "TVSSCS currency must be INR"
        assert vrllog_dict["currency"] == "INR", "VRLLOG currency must be INR"
        assert tvsscs_dict["roe"] == 5.62, f"TVSSCS ROE should be 5.62, got {tvsscs_dict['roe']}"
        print("\nALL ASSERTIONS PASSED PERFECTLY!")

if __name__ == "__main__":
    asyncio.run(verify_fixes())
