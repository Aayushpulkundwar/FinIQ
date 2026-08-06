import asyncio
import json
from uuid import UUID
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.financial import FinancialPeriod, FinancialStatement, FinancialMetric, FinancialEvidence, FinancialMetricProvenance

COMPANY_ID = UUID("3ec17afd-e43d-4cdc-8edb-89eed257d305")

async def deep_audit():
    async with SessionLocal() as db:
        print("==================================================")
        print("1. TVSSCS DB RECORDS DETAILED FIELD INSPECTION")
        print("==================================================")
        stmt = (
            select(FinancialPeriod, FinancialStatement, FinancialMetric)
            .join(FinancialStatement, FinancialStatement.period_id == FinancialPeriod.id)
            .outerjoin(FinancialMetric, FinancialMetric.statement_id == FinancialStatement.id)
            .where(FinancialPeriod.company_id == COMPANY_ID)
        )
        res = await db.execute(stmt)
        rows = res.all()
        for period, statement, metric in rows:
            print(f"PERIOD ID: {period.id}")
            print(f"  Company ID: {period.company_id}")
            print(f"  Fiscal Year: {period.fiscal_year}")
            print(f"  Period Type: {period.period_type}")
            print(f"  Currency: '{period.currency}'")
            print(f"  Created At: {period.created_at}")
            print(f"STATEMENT ID: {statement.id}")
            print(f"  Revenue: {statement.revenue}")
            print(f"  Operating Profit / EBIT: {statement.operating_income}")
            print(f"  EBITDA: {statement.ebitda}")
            print(f"  Net Profit: {statement.net_profit}")
            print(f"  Total Assets: {statement.total_assets}")
            print(f"  Total Liabilities: {statement.total_liabilities}")
            print(f"  Shareholders Equity: {statement.shareholders_equity}")
            print(f"  Operating Cash Flow: {statement.operating_cash_flow}")
            print(f"  Free Cash Flow: {statement.free_cash_flow}")
            print(f"  Created At: {statement.created_at}")

            # Check evidence
            ev_stmt = select(FinancialEvidence).where(FinancialEvidence.statement_id == statement.id)
            ev_res = await db.execute(ev_stmt)
            ev_rows = ev_res.scalars().all()
            print(f"  EVIDENCE ITEMS COUNT: {len(ev_rows)}")
            for ev in ev_rows:
                print(f"    - Field: {ev.financial_field} | Extracted Val: {ev.extracted_value} | Doc: {ev.document_title} | Page: {ev.page_number}")
                print(f"      Text Snippet: {ev.chunk_text[:150]}...")

            if metric:
                print(f"METRIC ID: {metric.id}")
                print(f"  EBITDA Margin: {metric.ebitda_margin}")
                print(f"  Net Profit Margin: {metric.net_profit_margin}")
                print(f"  ROE: {metric.roe}")
                print(f"  ROCE: {metric.roce}")
                print(f"  Debt to Equity: {metric.debt_to_equity}")
                print(f"  Current Ratio: {metric.current_ratio}")
                print(f"  Created At: {metric.created_at}")

                # Check provenance
                prov_stmt = select(FinancialMetricProvenance).where(FinancialMetricProvenance.metric_id == metric.id)
                prov_res = await db.execute(prov_stmt)
                prov_rows = prov_res.scalars().all()
                print(f"  PROVENANCE ITEMS COUNT: {len(prov_rows)}")
                for pr in prov_rows:
                    print(f"    - Metric: {pr.metric_name} | Formula: {pr.formula} | Inputs: {pr.input_fields}")

        print("\n==================================================")
        print("2. ALL FINANCIAL PERIODS FOR ALL COMPANIES")
        print("==================================================")
        comp_res = await db.execute(select(Company))
        companies = comp_res.scalars().all()
        for c in companies:
            fp_res = await db.execute(select(FinancialPeriod).where(FinancialPeriod.company_id == c.id))
            periods = fp_res.scalars().all()
            print(f"Company: {c.company_name} ({c.ticker_symbol}) | ID: {c.id} | Periods Count: {len(periods)}")

if __name__ == "__main__":
    asyncio.run(deep_audit())
