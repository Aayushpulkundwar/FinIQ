import asyncio
import json
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.financial import FinancialPeriod, FinancialStatement, FinancialMetric

async def audit_phase1():
    async with SessionLocal() as db:
        print("==================================================")
        print("1. QUERYING ALL FINANCIAL PERIODS & CURRENCY MISLABELS")
        print("==================================================")
        stmt = (
            select(FinancialPeriod, Company, FinancialStatement, FinancialMetric)
            .join(Company, Company.id == FinancialPeriod.company_id)
            .outerjoin(FinancialStatement, FinancialStatement.period_id == FinancialPeriod.id)
            .outerjoin(FinancialMetric, FinancialMetric.statement_id == FinancialStatement.id)
            .order_by(Company.ticker_symbol, FinancialPeriod.fiscal_year.desc())
        )
        res = await db.execute(stmt)
        rows = res.all()

        print(f"Total Financial Period Rows in Database: {len(rows)}\n")

        affected_periods = []
        for period, company, statement, metric in rows:
            is_mislabeled = False
            # Determine expected currency based on exchange / company country
            expected_currency = "INR" if company.exchange in ["NSE", "BSE"] or "India" in (company.country or "India") else "USD"
            
            if period.currency != expected_currency:
                is_mislabeled = True
                affected_periods.append({
                    "period_id": str(period.id),
                    "company_name": company.company_name,
                    "ticker": company.ticker_symbol,
                    "exchange": company.exchange,
                    "fiscal_year": period.fiscal_year,
                    "current_currency": period.currency,
                    "expected_currency": expected_currency,
                    "raw_revenue": float(statement.revenue) if statement and statement.revenue else None,
                    "raw_net_profit": float(statement.net_profit) if statement and statement.net_profit else None,
                    "raw_roe": float(metric.roe) if metric and metric.roe else None,
                })

            status_mark = "MISLABELED" if is_mislabeled else "CORRECT"
            print(f"[{status_mark}] Company: {company.company_name} ({company.ticker_symbol}) | FY{period.fiscal_year} ({period.period_type})")
            print(f"    Current Currency in DB: '{period.currency}' | Expected: '{expected_currency}' | Exchange: {company.exchange}")
            if statement:
                print(f"    Revenue: {statement.revenue} | Net Profit: {statement.net_profit}")
            if metric:
                print(f"    ROE: {metric.roe} | EBITDA Margin: {metric.ebitda_margin} | Net Margin: {metric.net_profit_margin}")
            print()

        print("==================================================")
        print("SUMMARY OF CURRENCY MISLABELED PERIODS")
        print("==================================================")
        print(f"Mislabeled Rows Count: {len(affected_periods)}")
        print(json.dumps(affected_periods, indent=2))

if __name__ == "__main__":
    asyncio.run(audit_phase1())
