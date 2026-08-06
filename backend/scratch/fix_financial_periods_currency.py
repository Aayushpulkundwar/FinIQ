import asyncio
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.financial import FinancialPeriod, FinancialStatement, FinancialMetric

async def fix_mislabeled_currencies():
    async with SessionLocal() as db:
        print("==================================================")
        print("EXECUTING ONE-TIME DATA CORRECTION SCRIPT")
        print("==================================================")
        
        stmt = (
            select(FinancialPeriod, Company)
            .join(Company, Company.id == FinancialPeriod.company_id)
        )
        res = await db.execute(stmt)
        rows = res.all()

        updated_count = 0
        for period, company in rows:
            exchange = (company.exchange or "").upper()
            ticker = (company.ticker_symbol or "").upper()
            isin = (company.isin or "").upper()

            # Determine true reporting currency
            if exchange in ["NSE", "BSE"] or isin.startswith("INE") or ticker.endswith(".NS") or ticker.endswith(".BO"):
                target_currency = "INR"
            elif exchange in ["NASDAQ", "NYSE", "AMEX"] or isin.startswith("US"):
                target_currency = "USD"
            elif exchange in ["LSE"] or isin.startswith("GB"):
                target_currency = "GBP"
            else:
                target_currency = period.currency  # Preserve if unknown/other

            if period.currency != target_currency:
                print(f"[FIXING] Period ID: {period.id} | Company: {company.company_name} ({company.ticker_symbol})")
                print(f"         Old Currency: '{period.currency}' -> New Currency: '{target_currency}'")
                period.currency = target_currency
                updated_count += 1
            else:
                print(f"[UNCHANGED] Period ID: {period.id} | Company: {company.company_name} | Currency: '{period.currency}'")

        if updated_count > 0:
            await db.commit()
            print(f"\nSuccessfully updated {updated_count} mislabeled FinancialPeriod rows in PostgreSQL.")
        else:
            print("\nNo mislabeled rows needed update.")

if __name__ == "__main__":
    asyncio.run(fix_mislabeled_currencies())
