import asyncio
import json
from app.services.financial_ratios_scraper import fetch_financial_ratios

async def main():
    r1 = await fetch_financial_ratios("TVSSCS", "NSE")
    print("TVSSCS ratios:")
    print(json.dumps(r1.model_dump(), indent=2))

    r2 = await fetch_financial_ratios("VRLLOG", "NSE")
    print("VRLLOG ratios:")
    print(json.dumps(r2.model_dump(), indent=2))

    r3 = await fetch_financial_ratios("MSFT", "NASDAQ")
    print("MSFT ratios:")
    print(json.dumps(r3.model_dump(), indent=2))

if __name__ == "__main__":
    asyncio.run(main())
