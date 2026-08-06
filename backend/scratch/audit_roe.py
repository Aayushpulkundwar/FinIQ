import asyncio
import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.financial import FinancialPeriod, FinancialStatement, FinancialMetric

async def audit_all_roe():
    async with SessionLocal() as db:
        print("=== AUDITING ALL FINANCIAL METRICS IN DB ===")
        stmt = (
            select(Company, FinancialPeriod, FinancialStatement, FinancialMetric)
            .join(FinancialPeriod, FinancialPeriod.company_id == Company.id)
            .join(FinancialStatement, FinancialStatement.period_id == FinancialPeriod.id)
            .outerjoin(FinancialMetric, FinancialMetric.statement_id == FinancialStatement.id)
        )
        res = await db.execute(stmt)
        rows = res.all()
        print(f"Total period/statement rows found: {len(rows)}")
        for company, period, statement, metric in rows:
            net_profit = statement.net_profit
            equity = statement.shareholders_equity
            calc_ratio = (net_profit / equity) if net_profit is not None and equity and equity != 0 else None
            roe_val = metric.roe if metric else None
            npm_val = metric.net_profit_margin if metric else None
            ebitda_m_val = metric.ebitda_margin if metric else None
            print(f"Company: {company.ticker_symbol} ({company.company_name}) | FY: {period.fiscal_year}")
            print(f"  Net Profit: {net_profit}, Shareholders Equity: {equity}")
            print(f"  Calc decimal ratio (NetProfit/Equity): {calc_ratio}")
            print(f"  Stored Metric ROE: {roe_val}")
            print(f"  Stored Metric NPM: {npm_val}")
            print(f"  Stored Metric EBITDA Margin: {ebitda_m_val}")
            print("-*20")

if __name__ == "__main__":
    asyncio.run(audit_all_roe())
