import sys
import os
sys.path.append(os.getcwd())

import asyncio
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.company import Company
from app.services.market_data import get_yfinance_dcf_inputs, _resolve_ticker
import yfinance as yf

async def run():
    db = SessionLocal()
    try:
        stmt = select(Company)
        res = await db.execute(stmt)
        companies = res.scalars().all()
        print("%-30s | %-10s | %-10s | %-15s | %-15s | %-7s | %-7s | %-20s" % 
              ("Name", "Ticker", "Exchange", "yf_ticker", "Sector", "RawBeta", "ResBeta", "Status"))
        print("-" * 130)
        for c in companies:
            if c.ticker_symbol == "string":
                continue
            yf_ticker = _resolve_ticker(c.ticker_symbol, c.exchange)
            # Fetch directly from yfinance to see what is returned
            ticker_obj = yf.Ticker(yf_ticker)
            try:
                info = ticker_obj.info or {}
            except Exception as e:
                info = {}
                print(f"Error getting info for {yf_ticker}: {e}")
            raw_beta = info.get("beta")
            
            # Now fetch via service to see the resolved inputs
            res_inputs = await get_yfinance_dcf_inputs(c.ticker_symbol, c.exchange)
            resolved_beta = res_inputs.get("beta")
            available = res_inputs.get("available")
            reason = res_inputs.get("reason")
            missing = res_inputs.get("missing", "")
            
            print(f"{c.company_name[:30]:<30} | {c.ticker_symbol:<10} | {c.exchange:<10} | {yf_ticker:<15} | {c.sector[:15]:<15} | {str(raw_beta):<7} | {str(resolved_beta):<7} | Avail={available} ({reason or missing})")
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(run())
