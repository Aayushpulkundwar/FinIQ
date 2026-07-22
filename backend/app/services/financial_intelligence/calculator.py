from typing import Optional, Tuple, List
from app.schemas.financial import FinancialStatementData, FinancialMetricsData, MetricProvenance


def _safe_divide(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    """Returns numerator/denominator or None if either is None or denominator is zero."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return round(numerator / denominator, 4)


class MetricCalculator:
    """
    Pure-function financial ratio calculator.
    All methods return (value, MetricProvenance) pairs for full provenance tracking.
    Handles divide-by-zero and missing values gracefully.
    """

    @staticmethod
    def calculate_ebitda_margin(
        ebitda: Optional[float], revenue: Optional[float]
    ) -> Tuple[Optional[float], MetricProvenance]:
        value = _safe_divide(ebitda, revenue)
        if value is not None:
            value = round(value * 100, 4)  # as percentage
        return value, MetricProvenance(
            metric_name="ebitda_margin",
            formula="ebitda / revenue * 100",
            input_fields=["ebitda", "revenue"]
        )

    @staticmethod
    def calculate_net_profit_margin(
        net_profit: Optional[float], revenue: Optional[float]
    ) -> Tuple[Optional[float], MetricProvenance]:
        value = _safe_divide(net_profit, revenue)
        if value is not None:
            value = round(value * 100, 4)
        return value, MetricProvenance(
            metric_name="net_profit_margin",
            formula="net_profit / revenue * 100",
            input_fields=["net_profit", "revenue"]
        )

    @staticmethod
    def calculate_roe(
        net_profit: Optional[float], shareholders_equity: Optional[float]
    ) -> Tuple[Optional[float], MetricProvenance]:
        value = _safe_divide(net_profit, shareholders_equity)
        if value is not None:
            value = round(value * 100, 4)
        return value, MetricProvenance(
            metric_name="roe",
            formula="net_profit / shareholders_equity * 100",
            input_fields=["net_profit", "shareholders_equity"]
        )

    @staticmethod
    def calculate_roce(
        operating_income: Optional[float],
        total_assets: Optional[float],
        total_liabilities: Optional[float]
    ) -> Tuple[Optional[float], MetricProvenance]:
        capital_employed = None
        if total_assets is not None and total_liabilities is not None:
            capital_employed = total_assets - total_liabilities
        value = _safe_divide(operating_income, capital_employed)
        if value is not None:
            value = round(value * 100, 4)
        return value, MetricProvenance(
            metric_name="roce",
            formula="operating_income / (total_assets - total_liabilities) * 100",
            input_fields=["operating_income", "total_assets", "total_liabilities"]
        )

    @staticmethod
    def calculate_debt_to_equity(
        total_liabilities: Optional[float], shareholders_equity: Optional[float]
    ) -> Tuple[Optional[float], MetricProvenance]:
        value = _safe_divide(total_liabilities, shareholders_equity)
        return value, MetricProvenance(
            metric_name="debt_to_equity",
            formula="total_liabilities / shareholders_equity",
            input_fields=["total_liabilities", "shareholders_equity"]
        )

    @staticmethod
    def calculate_revenue_growth_yoy(
        current_revenue: Optional[float], previous_revenue: Optional[float]
    ) -> Tuple[Optional[float], MetricProvenance]:
        value = None
        if current_revenue is not None and previous_revenue and previous_revenue != 0:
            value = round((current_revenue - previous_revenue) / abs(previous_revenue) * 100, 4)
        return value, MetricProvenance(
            metric_name="revenue_growth_yoy",
            formula="(current_revenue - previous_revenue) / abs(previous_revenue) * 100",
            input_fields=["revenue (current year)", "revenue (previous year)"]
        )

    @staticmethod
    def calculate_eps_growth(
        current_eps: Optional[float], previous_eps: Optional[float]
    ) -> Tuple[Optional[float], MetricProvenance]:
        value = None
        if current_eps is not None and previous_eps and previous_eps != 0:
            value = round((current_eps - previous_eps) / abs(previous_eps) * 100, 4)
        return value, MetricProvenance(
            metric_name="eps_growth",
            formula="(current_eps - previous_eps) / abs(previous_eps) * 100",
            input_fields=["eps (current year)", "eps (previous year)"]
        )

    @staticmethod
    def calculate_free_cash_flow_yield(
        free_cash_flow: Optional[float], revenue: Optional[float]
    ) -> Tuple[Optional[float], MetricProvenance]:
        value = _safe_divide(free_cash_flow, revenue)
        if value is not None:
            value = round(value * 100, 4)
        return value, MetricProvenance(
            metric_name="free_cash_flow_yield",
            formula="free_cash_flow / revenue * 100",
            input_fields=["free_cash_flow", "revenue"]
        )

    @staticmethod
    def calculate_current_ratio(
        operating_cash_flow: Optional[float], total_liabilities: Optional[float]
    ) -> Tuple[Optional[float], MetricProvenance]:
        """
        Approximates current ratio using operating cash flow / total liabilities
        when current assets and current liabilities are unavailable from chunks.
        """
        value = _safe_divide(operating_cash_flow, total_liabilities)
        return value, MetricProvenance(
            metric_name="current_ratio",
            formula="operating_cash_flow / total_liabilities (proxy)",
            input_fields=["operating_cash_flow", "total_liabilities"]
        )

    @classmethod
    def calculate_all(
        cls,
        stmt: "FinancialStatementData",
        prev_stmt: Optional["FinancialStatementData"] = None
    ) -> Tuple[FinancialMetricsData, List[MetricProvenance]]:
        """
        Calculates all 9 financial metrics from a FinancialStatementData instance.
        If prev_stmt is provided, YoY growth metrics are computed.
        Returns (FinancialMetricsData, List[MetricProvenance]).
        """
        provenance: List[MetricProvenance] = []
        kwargs = {}

        # 1. EBITDA Margin
        v, p = cls.calculate_ebitda_margin(stmt.ebitda, stmt.revenue)
        kwargs["ebitda_margin"] = v
        if v is not None:
            provenance.append(p)

        # 2. Net Profit Margin
        v, p = cls.calculate_net_profit_margin(stmt.net_profit, stmt.revenue)
        kwargs["net_profit_margin"] = v
        if v is not None:
            provenance.append(p)

        # 3. ROE
        v, p = cls.calculate_roe(stmt.net_profit, stmt.shareholders_equity)
        kwargs["roe"] = v
        if v is not None:
            provenance.append(p)

        # 4. ROCE
        v, p = cls.calculate_roce(stmt.operating_income, stmt.total_assets, stmt.total_liabilities)
        kwargs["roce"] = v
        if v is not None:
            provenance.append(p)

        # 5. Debt to Equity
        v, p = cls.calculate_debt_to_equity(stmt.total_liabilities, stmt.shareholders_equity)
        kwargs["debt_to_equity"] = v
        if v is not None:
            provenance.append(p)

        # 6. Revenue Growth YoY
        prev_revenue = prev_stmt.revenue if prev_stmt else None
        v, p = cls.calculate_revenue_growth_yoy(stmt.revenue, prev_revenue)
        kwargs["revenue_growth_yoy"] = v
        if v is not None:
            provenance.append(p)

        # 7. EPS Growth
        prev_eps = prev_stmt.eps if prev_stmt else None
        v, p = cls.calculate_eps_growth(stmt.eps, prev_eps)
        kwargs["eps_growth"] = v
        if v is not None:
            provenance.append(p)

        # 8. Free Cash Flow Yield
        v, p = cls.calculate_free_cash_flow_yield(stmt.free_cash_flow, stmt.revenue)
        kwargs["free_cash_flow_yield"] = v
        if v is not None:
            provenance.append(p)

        # 9. Current Ratio (proxy)
        v, p = cls.calculate_current_ratio(stmt.operating_cash_flow, stmt.total_liabilities)
        kwargs["current_ratio"] = v
        if v is not None:
            provenance.append(p)

        return FinancialMetricsData(**kwargs), provenance
