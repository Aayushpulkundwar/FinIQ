import asyncio
from uuid import UUID
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.company import Company
from app.api.v1.routers.company import get_company_financial_summary

async def check():
    db = SessionLocal()
    try:
        stmt = select(Company)
        res = await db.execute(stmt)
        companies = res.scalars().all()
        
        print(f"Total companies found in DB: {len(companies)}")
        print("-" * 80)
        
        for c in companies:
            try:
                summary = await get_company_financial_summary(c.id, db)
                print(f"Ticker: {c.ticker_symbol:<10} | Company: {c.company_name:<40} | Available: {summary.available:<5} | Year: {summary.fiscal_year} | Source: {summary.revenue_source} | Revenue: {summary.revenue}")
                if not summary.available:
                    print(f"  --> Reason: {summary.reason}")
            except Exception as e:
                print(f"Ticker: {c.ticker_symbol:<10} | Company: {c.company_name:<40} | FAILED with exception: {e}")
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(check())
