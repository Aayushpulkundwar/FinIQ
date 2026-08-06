import asyncio
import json
from uuid import UUID
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.financial import FinancialPeriod, FinancialStatement, FinancialMetric
from app.models.document import Document
from app.services.yahoo_finance_summary import get_financial_summary
from app.services.market_data import _resolve_ticker

COMPANY_ID = UUID("3ec17afd-e43d-4cdc-8edb-89eed257d305")

async def audit_tvsscs():
    async with SessionLocal() as db:
        print("==================================================")
        print("1. DB COMPANY INFO")
        print("==================================================")
        comp = await db.get(Company, COMPANY_ID)
        if not comp:
            print("Company not found!")
            return
        print(f"Name: {comp.company_name}")
        print(f"Ticker: {comp.ticker_symbol}, Exchange: {comp.exchange}")
        resolved_ticker = _resolve_ticker(comp.ticker_symbol, comp.exchange or "")
        print(f"Resolved yfinance ticker: {resolved_ticker}\n")

        print("==================================================")
        print("2. DATABASE FINANCIAL PERIODS / STATEMENTS / METRICS")
        print("==================================================")
        stmt = (
            select(FinancialPeriod, FinancialStatement, FinancialMetric)
            .join(FinancialStatement, FinancialStatement.period_id == FinancialPeriod.id)
            .outerjoin(FinancialMetric, FinancialMetric.statement_id == FinancialStatement.id)
            .where(FinancialPeriod.company_id == COMPANY_ID)
            .order_by(FinancialPeriod.fiscal_year.desc())
        )
        res = await db.execute(stmt)
        rows = res.all()
        print(f"Found {len(rows)} annual/quarterly DB financial records:")
        for period, statement, metric in rows:
            print(f"--- Period: FY{period.fiscal_year} ({period.period_type}) | Currency: {period.currency} ---")
            print(f"  Statement ID: {statement.id}")
            print(f"  Raw Revenue: {statement.revenue} (type: {type(statement.revenue)})")
            print(f"  Raw EBITDA: {statement.ebitda} (type: {type(statement.ebitda)})")
            print(f"  Raw Net Profit: {statement.net_profit} (type: {type(statement.net_profit)})")
            if metric:
                print(f"  Metric ID: {metric.id}")
                print(f"  Raw ROE: {metric.roe} (type: {type(metric.roe)})")
                print(f"  Raw ROA: {metric.roa}")
                print(f"  Raw Debt-to-Equity: {metric.debt_to_equity}")
            else:
                print("  No FinancialMetric record attached.")

            # Let's inspect raw balance sheet & income statement fields stored in FinancialStatement if any
            meta = statement.statement_metadata or {}
            print(f"  Metadata / Raw fields: {meta}")
            print()

        print("==================================================")
        print("3. INGESTED DOCUMENTS FOR THIS COMPANY")
        print("==================================================")
        doc_stmt = select(Document).where(Document.company_id == COMPANY_ID)
        doc_res = await db.execute(doc_stmt)
        docs = doc_res.scalars().all()
        print(f"Found {len(docs)} documents:")
        for d in docs:
            print(f"  Doc ID: {d.id} | Title: {d.title} | Status: {d.processing_status} | Created: {d.created_at}")
        print()

        print("==================================================")
        print("4. YAHOO FINANCE SUMMARY SERVICE OUTPUT")
        print("==================================================")
        yf_summary = await get_financial_summary(comp.ticker_symbol, comp.exchange or "")
        print("yfinance get_financial_summary output:")
        print(json.dumps(yf_summary, indent=2))
        print()

if __name__ == "__main__":
    asyncio.run(audit_tvsscs())
