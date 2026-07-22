import sys
import os
sys.path.append(os.getcwd())

import asyncio
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.financial import FinancialPeriod
from app.services.valuation import ValuationService

async def run():
    db = SessionLocal()
    val_svc = ValuationService(db)
    try:
        stmt = select(Company)
        res = await db.execute(stmt)
        companies = res.scalars().all()
        print("%-30s | %-10s | %-6s | %-22s | %-6s | %-10s | %-10s" % 
              ("Name", "Ticker", "Beta", "BetaSource", "WACC", "WaccClmpFb", "Intrinsic"))
        print("-" * 110)
        for c in companies:
            if c.ticker_symbol == "string":
                continue
            try:
                # Find latest fiscal year in DB to bypass RAG time-outs
                period_stmt = select(FinancialPeriod).where(
                    FinancialPeriod.company_id == c.id
                ).order_by(FinancialPeriod.fiscal_year.desc()).limit(1)
                period_res = await db.execute(period_stmt)
                period = period_res.scalars().first()
                
                fy = period.fiscal_year if period else None
                
                # Calculate valuation
                val_summary = await val_svc.calculate_valuation(c.id, fiscal_year=fy)
                # Print details
                print(f"{c.company_name[:30]:<30} | {c.ticker_symbol:<10} | "
                      f"{val_summary.beta:<6} | {val_summary.beta_source:<22} | "
                      f"{val_summary.wacc_details.wacc:<6} | "
                      f"{str(val_summary.wacc_clamped_due_to_fallback_beta):<10} | "
                      f"{val_summary.dcf_details.intrinsic_share_price:<10}")
            except Exception as e:
                print(f"{c.company_name[:30]:<30} | {c.ticker_symbol:<10} | ERROR: {e}")
    except Exception as e:
        print(f"MAIN ERROR: {e}")
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(run())
