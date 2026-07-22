from typing import List, Optional
from uuid import UUID
from loguru import logger
from app.repositories.financial import FinancialRepository
from app.schemas.financial import TrendPoint


TREND_STABLE_THRESHOLD = 0.02  # 2% change = Stable


def _classify_trend(current: Optional[float], previous: Optional[float]) -> str:
    """Classifies trend direction based on percentage change."""
    if current is None or previous is None or previous == 0:
        return "Stable"
    change = (current - previous) / abs(previous)
    if change > TREND_STABLE_THRESHOLD:
        return "Increasing"
    elif change < -TREND_STABLE_THRESHOLD:
        return "Declining"
    return "Stable"


class TrendAnalyzer:
    """
    Fetches multi-period historical financial statements from the database and
    classifies revenue, net profit, and EPS trends over time.
    """
    def __init__(self, repository: FinancialRepository):
        self.repository = repository

    async def analyze(self, company_id: UUID, limit: int = 6) -> List[TrendPoint]:
        """
        Fetches up to `limit` historical statements and builds structured trend data.
        Trend direction is calculated relative to the immediately preceding period.
        """
        statements = await self.repository.get_statements_by_company(company_id, limit=limit)
        logger.bind(company_id=str(company_id), count=len(statements)).info(
            "TrendAnalyzer: fetched historical statements."
        )

        if not statements:
            return []

        # Import here to avoid circular dependency
        from sqlalchemy import select
        from app.models.financial import FinancialPeriod

        # Fetch period metadata for each statement
        period_ids = [s.period_id for s in statements]
        period_map = {}
        for s in statements:
            result = await self.repository.db.get(FinancialPeriod, s.period_id)
            if result:
                period_map[s.id] = result

        trend_points: List[TrendPoint] = []

        for i, stmt in enumerate(statements):
            period = period_map.get(stmt.id)
            prev_stmt = statements[i + 1] if i + 1 < len(statements) else None

            revenue = float(stmt.revenue) if stmt.revenue is not None else None
            net_profit = float(stmt.net_profit) if stmt.net_profit is not None else None
            eps = float(stmt.eps) if stmt.eps is not None else None

            prev_revenue = float(prev_stmt.revenue) if prev_stmt and prev_stmt.revenue is not None else None

            direction = _classify_trend(revenue, prev_revenue)

            trend_points.append(TrendPoint(
                fiscal_year=period.fiscal_year if period else 0,
                period_type=period.period_type.value if period else "annual",
                revenue=revenue,
                net_profit=net_profit,
                eps=eps,
                trend_direction=direction,
            ))

        return trend_points
