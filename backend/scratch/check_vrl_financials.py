import asyncio
from uuid import UUID
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.financial import FinancialPeriod, FinancialStatement, FinancialMetric

async def check():
    db = SessionLocal()
    try:
        co_id = UUID("30541b63-c9b3-411c-a128-a05a9e39c7c7")
        stmt = (
            select(FinancialPeriod, FinancialStatement, FinancialMetric)
            .join(FinancialStatement, FinancialStatement.period_id == FinancialPeriod.id)
            .outerjoin(FinancialMetric, FinancialMetric.statement_id == FinancialStatement.id)
            .where(FinancialPeriod.company_id == co_id)
        )
        res = await db.execute(stmt)
        rows = res.all()
        print(f"Total financial periods found for VRL: {len(rows)}")
        for period, statement, metric in rows:
            print(f"Year: {period.fiscal_year} | Type: {period.period_type} | Currency: {period.currency}")
            print(f"  Revenue: {statement.revenue} | EBITDA: {statement.ebitda} | Net Income: {statement.net_profit}")
            if metric:
                print(f"  ROE: {metric.roe}")
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(check())
