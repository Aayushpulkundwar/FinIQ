import argparse
import asyncio
import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from loguru import logger

from app.db.session import SessionLocal
from app.models.company import Company
from app.models.financial import FinancialPeriod, FinancialStatement, FinancialMetric
from app.services.financial_intelligence.calculator import MetricCalculator

async def run_backfill(apply_changes: bool = False, tolerance: float = 1.0):
    async with SessionLocal() as db:
        mode_str = "APPLY (WRITING TO DB)" if apply_changes else "DRY-RUN (NO DB WRITES)"
        logger.info(f"=== ROE BACKFILL AUDIT [{mode_str}] (Tolerance threshold: {tolerance}%) ===")

        stmt = (
            select(Company, FinancialPeriod, FinancialStatement, FinancialMetric)
            .join(FinancialPeriod, FinancialPeriod.company_id == Company.id)
            .join(FinancialStatement, FinancialStatement.period_id == FinancialPeriod.id)
            .outerjoin(FinancialMetric, FinancialMetric.statement_id == FinancialStatement.id)
        )
        res = await db.execute(stmt)
        rows = res.all()
        
        logger.info(f"Inspecting {len(rows)} statement/metric records across database...")

        updated_count = 0
        skipped_count = 0

        for company, period, statement, metric in rows:
            net_profit = float(statement.net_profit) if statement.net_profit is not None else None
            equity = float(statement.shareholders_equity) if statement.shareholders_equity is not None else None

            if net_profit is None or equity is None or equity == 0:
                logger.debug(f"[{company.ticker_symbol} FY{period.fiscal_year}] Missing net_profit or equity. Skipping.")
                continue

            recalculated_roe, _ = MetricCalculator.calculate_roe(net_profit, equity)
            stored_roe = float(metric.roe) if metric and metric.roe is not None else None

            if recalculated_roe is None:
                continue

            delta = abs(recalculated_roe - stored_roe) if stored_roe is not None else float("inf")

            if delta > tolerance:
                logger.warning(
                    f"[{company.ticker_symbol} FY{period.fiscal_year}] OUTLIER DETECTED! "
                    f"Stored ROE: {stored_roe}, Recalculated ROE: {recalculated_roe}, Delta: {delta:.4f}"
                )
                if metric:
                    if apply_changes:
                        metric.roe = recalculated_roe
                        updated_count += 1
                        logger.info(f"  -> Updated metric.roe to {recalculated_roe}")
                    else:
                        logger.info(f"  -> [Dry-Run] Would update metric.roe from {stored_roe} to {recalculated_roe}")
            else:
                logger.info(
                    f"[{company.ticker_symbol} FY{period.fiscal_year}] OK - Stored ROE: {stored_roe}, "
                    f"Recalculated ROE: {recalculated_roe}, Delta: {delta:.4f}"
                )
                skipped_count += 1

        if apply_changes and updated_count > 0:
            await db.commit()
            logger.info(f"Successfully committed {updated_count} ROE updates to database.")
        else:
            logger.info(f"Finished audit. Outliers updated/flagged: {updated_count}, Sane records: {skipped_count}.")


def main():
    parser = argparse.ArgumentParser(description="Audit and backfill ROE metrics in database.")
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Apply database writes. Default is --dry-run."
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1.0,
        help="Tolerance threshold for delta (recalculated - stored). Default 1.0."
    )
    args = parser.parse_args()

    asyncio.run(run_backfill(apply_changes=args.apply, tolerance=args.tolerance))

if __name__ == "__main__":
    main()
