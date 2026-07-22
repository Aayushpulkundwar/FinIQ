import time
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.investment import ValuationSummary, WaccDetails, DcfDetails, SensitivityPoint
from app.services.financial_intelligence.service import FinancialIntelligenceService
from app.services.company import CompanyService

EQUITY_RISK_PREMIUM_DEFAULT = 0.055

# ─────────────────────────────────────────────────────────────────────────────
# Pure DCF function — no DB / session dependency
# ─────────────────────────────────────────────────────────────────────────────

def compute_dcf_intrinsic_value(
    baseline_fcf: float,
    fcf_growth_rate: float,
    wacc: float,
    shares_outstanding: float,
    perpetuity_growth_rate: float = 0.02,
    debt_proxy: float = 0.0,
    projection_years: int = 5,
    cash: float = 0.0,
    debt: Optional[float] = None,
) -> Tuple[float, List[float], float, float, float]:
    """
    Compute the DCF intrinsic value per share given plain scalar inputs.

    This is a pure function with no DB or session dependency.  Both the
    DB-backed ValuationService and the live-recommendation flow call this
    function after fetching and clamping their respective inputs.

    Callers are responsible for clamping WACC and FCF growth rate BEFORE
    calling this function.  The internal clamp_wacc() call has been removed
    to eliminate silent double-clamping and to keep this function truly pure.

    Returns
    -------
    (intrinsic_share_price, projected_fcfs, terminal_value, enterprise_value, equity_value)
    """

    if perpetuity_growth_rate < 0:
        raise ValueError("Terminal growth rate cannot be negative.")
    if wacc <= perpetuity_growth_rate:
        raise ValueError("WACC must be strictly greater than terminal growth rate.")
    if wacc > 0.25:
        raise ValueError("WACC cannot exceed 25%.")

    if wacc < 0.08 or wacc > 0.12:
        logger.warning(f"Configured WACC {wacc:.2%} is outside typical 8-12% range.")
    if perpetuity_growth_rate < 0.02 or perpetuity_growth_rate > 0.04:
        logger.warning(f"Configured perpetuity growth rate {perpetuity_growth_rate:.2%} is outside typical 2-4% range.")

    actual_growth_g = perpetuity_growth_rate

    # Project FCFs
    projected_fcfs: List[float] = []
    current_fcf = baseline_fcf
    for _ in range(projection_years):
        current_fcf = current_fcf * (1 + fcf_growth_rate)
        projected_fcfs.append(round(current_fcf, 2))

    # PV of projected FCFs
    pv_of_fcfs = sum(
        fcf / ((1 + wacc) ** (idx + 1))
        for idx, fcf in enumerate(projected_fcfs)
    )

    # Terminal value (Gordon Growth perpetuity formula)
    terminal_value = projected_fcfs[-1] * (1 + actual_growth_g) / (wacc - actual_growth_g)
    pv_of_terminal_value = terminal_value / ((1 + wacc) ** projection_years)

    enterprise_value = pv_of_fcfs + pv_of_terminal_value
    debt_val = debt if debt is not None else debt_proxy
    equity_value = enterprise_value + cash - debt_val
    intrinsic_share_price = equity_value / shares_outstanding if shares_outstanding > 0 else 0.0

    return (
        round(intrinsic_share_price, 2),
        projected_fcfs,
        round(terminal_value, 2),
        round(enterprise_value, 2),
        round(equity_value, 2),
    )


class ValuationService:
    """
    Valuation Engine responsible for calculating WACC, performing DCF valuation,
    terminal/enterprise/equity value calculations, intrinsic share price estimation,
    and sensitivity grid analysis.

    Uses financial statement data retrieved from the database via FinancialIntelligenceService.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.financial_service = FinancialIntelligenceService(db)
        self.company_service = CompanyService(db)

    async def calculate_valuation(
        self,
        company_id: UUID,
        fiscal_year: Optional[int] = None,
        risk_free_rate: Optional[float] = None,
        equity_risk_premium: Optional[float] = None,
        beta: Optional[float] = None,
        pretax_cost_of_debt: Optional[float] = None,
        tax_rate: Optional[float] = None,
        perpetuity_growth_rate: float = 0.02,
        shares_outstanding: Optional[float] = None,
    ) -> ValuationSummary:
        """
        Runs the WACC, DCF, and Sensitivity analysis.
        """
        logger.bind(company_id=str(company_id), fiscal_year=fiscal_year).info(
            "ValuationService: starting calculation."
        )

        # ── Fetch financial statement data ────────────────────────────────────
        # Run financial analysis pipeline to ensure statement and ratios are persisted
        fin_report = await self.financial_service.analyze(company_id, fiscal_year=fiscal_year)
        company = await self.company_service.repository.get(company_id)

        stmt = fin_report.latest_statement
        metrics = fin_report.calculated_metrics

        cash = 0.0
        debt = float(stmt.total_liabilities) if stmt.total_liabilities is not None else 0.0
        current_price = None
        dcf_inputs = {}

        # Resolve real shares outstanding, cash, debt, and tax rate from yfinance
        if company and company.ticker_symbol:
            try:
                from app.services.market_data import get_yfinance_dcf_inputs
                dcf_inputs_fetched = await get_yfinance_dcf_inputs(company.ticker_symbol, company.exchange or "")
                if dcf_inputs_fetched.get("available"):
                    dcf_inputs = dcf_inputs_fetched
                    if dcf_inputs.get("shares_outstanding"):
                        shares_outstanding = dcf_inputs["shares_outstanding"]
                    if dcf_inputs.get("cash") is not None:
                        cash = dcf_inputs["cash"]
                    if dcf_inputs.get("debt") is not None:
                        debt = dcf_inputs["debt"]
                    if dcf_inputs.get("tax_rate") is not None:
                        tax_rate = dcf_inputs["tax_rate"]
                    if dcf_inputs.get("current_price") is not None:
                        current_price = dcf_inputs["current_price"]
                    logger.info(f"ValuationService: resolved from yfinance shares={shares_outstanding}, cash={cash}, debt={debt}, tax_rate={tax_rate}, price={current_price} for {company.ticker_symbol}")
            except Exception as e:
                logger.warning(f"ValuationService: failed to resolve cash/debt/shares/tax_rate from yfinance: {e}")

        # Resolve dynamic CAPM inputs
        live_beta = dcf_inputs.get("beta")
        from app.services.valuation_utils import validate_beta
        if live_beta is not None:
            beta = live_beta
            beta_source = dcf_inputs.get("beta_source", "yfinance_valid")
        else:
            beta, beta_source = validate_beta(None, company.sector if company else None)

        live_rf = dcf_inputs.get("risk_free_rate")
        if live_rf is not None:
            risk_free_rate = live_rf
        else:
            risk_free_rate = risk_free_rate or 0.040

        erp = equity_risk_premium or EQUITY_RISK_PREMIUM_DEFAULT

        # ── 1. WACC Calculation ───────────────────────────────────────────────
        cost_of_equity = risk_free_rate + (beta * erp)

        tax_rate_estimated = dcf_inputs.get("tax_rate_estimated", False)
        if tax_rate is None:
            tax_rate = dcf_inputs.get("tax_rate") or 0.21
            tax_rate_estimated = True

        cost_of_debt_estimated = dcf_inputs.get("cost_of_debt_estimated", False)
        if pretax_cost_of_debt is None:
            pretax_cost_of_debt = dcf_inputs.get("cost_of_debt") or 0.060
            cost_of_debt_estimated = True

        cost_of_debt = pretax_cost_of_debt * (1 - tax_rate)

        # Capital Structure weights from total liabilities vs equity
        # Prefer Market Value of Equity if current_price and shares_outstanding are available.
        # Otherwise, fall back to Book Value of Equity from statement.
        equity_val = None
        resolved_shares = shares_outstanding or dcf_inputs.get("shares_outstanding") or 1_000_000_000.0
        if current_price is not None and current_price > 0 and resolved_shares > 0:
            equity_val = float(resolved_shares) * float(current_price)
            market_cap = equity_val
            logger.info(f"ValuationService: Using Market Value of Equity for WACC: {equity_val}")
        else:
            market_cap = None
            if stmt.shareholders_equity is not None and stmt.shareholders_equity > 0:
                equity_val = float(stmt.shareholders_equity)
                logger.info(f"ValuationService: Using Book Value of Equity for WACC: {equity_val}")

        debt_val = None
        if debt is not None and debt >= 0:
            debt_val = float(debt)
        elif stmt.total_liabilities is not None:
            debt_val = float(stmt.total_liabilities)

        if equity_val is not None and equity_val > 0 and debt_val is not None and debt_val >= 0:
            total_cap = equity_val + debt_val
            equity_weight = equity_val / total_cap
            debt_weight = debt_val / total_cap
        else:
            # Fallback to standard capital weights (80% equity / 20% debt)
            equity_weight = 0.80
            debt_weight = 0.20
            logger.info("ValuationService: Using fallback capital weights (80% equity / 20% debt)")

        wacc = (equity_weight * cost_of_equity) + (debt_weight * cost_of_debt)
        raw_wacc = wacc  # capture before clamping for diagnostics
        from app.services.valuation_utils import clamp_wacc_with_beta_check, check_double_clamp
        wacc, wacc_was_clamped, wacc_clamped_due_to_fallback_beta = clamp_wacc_with_beta_check(wacc, beta_source)
        if wacc_was_clamped:
            logger.info(
                f"ValuationService: raw WACC={raw_wacc:.4%} → clamped to {wacc:.4%} "
                f"for {company.company_name if company else 'unknown'}"
            )

        # ── 2. DCF Valuation — derive UFCF inputs then call pure function ─────────
        # UFCF = EBIT × (1 - Tax Rate) + Depreciation - CapEx - Change in Working Capital
        # Never use Net Income, EBITDA, or EBIT directly as FCF.
        
        # EBIT (operating_income)
        ebit = float(stmt.operating_income) if stmt.operating_income is not None else None
        if ebit is None:
            if dcf_inputs.get("ebit") is not None:
                ebit = float(dcf_inputs["ebit"])
                logger.info(f"ValuationService: EBIT was missing in DB, resolved from yfinance: {ebit}")
        
        # Depreciation & Amortization
        dep = None
        if stmt.ebitda is not None and stmt.operating_income is not None:
            dep = float(stmt.ebitda - stmt.operating_income)
            if dep < 0:
                dep = 0.0
        if dep is None:
            if dcf_inputs.get("depreciation") is not None:
                dep = float(dcf_inputs["depreciation"])
                logger.info(f"ValuationService: Depreciation was missing in DB, resolved from yfinance: {dep}")
        if dep is None:
            dep = 0.0

        # CapEx (always positive)
        capex = float(abs(stmt.capex)) if stmt.capex is not None else None
        if capex is None:
            if dcf_inputs.get("capex") is not None:
                capex = float(dcf_inputs["capex"])
                logger.info(f"ValuationService: CapEx was missing in DB, resolved from yfinance: {capex}")
        if capex is None:
            capex = 0.0

        # Change in Working Capital (Net Income + Dep - OCF)
        wcap = None
        if stmt.net_profit is not None and stmt.operating_cash_flow is not None:
            wcap = float(stmt.net_profit) + dep - float(stmt.operating_cash_flow)
        if wcap is None:
            if dcf_inputs.get("change_in_working_capital") is not None:
                wcap = float(dcf_inputs["change_in_working_capital"])
                logger.info(f"ValuationService: Change in Working Capital was missing in DB, resolved from yfinance: {wcap}")
        if wcap is None:
            wcap = 0.0

        # Free Cash Flow directly from DB statement if available
        fcf = float(stmt.free_cash_flow) if stmt.free_cash_flow is not None else None
        if fcf is None:
            if dcf_inputs.get("free_cash_flow") is not None:
                fcf = float(dcf_inputs["free_cash_flow"])
                logger.info(f"ValuationService: Free Cash Flow was missing in DB, resolved from yfinance: {fcf}")

        # Calculate UFCF as fallback
        ufcf_computed = None
        if ebit is not None and dep is not None and capex is not None and wcap is not None:
            ufcf_computed = ebit * (1 - tax_rate) + dep - capex - wcap

        if fcf is not None and fcf > 0:
            baseline_fcf = fcf
            logger.info(f"ValuationService: Using direct Free Cash Flow ({baseline_fcf}) as baseline FCF.")
        elif ufcf_computed is not None:
            baseline_fcf = ufcf_computed
            logger.info(f"ValuationService: Direct FCF is unavailable or non-positive. Using computed UFCF ({baseline_fcf}) as baseline FCF.")
        else:
            baseline_fcf = None

        # Log detailed intermediate valuation inputs before performing validation checks
        logger.info(
            f"DB-backed DCF Intermediate Valuation Inputs for {company.company_name if company else 'unknown'}:\n"
            f"  - Free Cash Flow (Direct): {fcf}\n"
            f"  - computed UFCF: {ufcf_computed}\n"
            f"  - Selected Baseline FCF: {baseline_fcf}\n"
            f"  - EBIT: {ebit}\n"
            f"  - Depreciation: {dep}\n"
            f"  - CapEx: {capex}\n"
            f"  - Change in Working Capital: {wcap}\n"
            f"  - Cash & Cash Equivalents: {cash}\n"
            f"  - Total Debt: {debt}\n"
            f"  - Shares Outstanding: {resolved_shares}\n"
            f"  - Tax Rate: {tax_rate}"
        )

        # Validate critical derived inputs
        missing_inputs = []
        if resolved_shares <= 0:
            missing_inputs.append("shares_outstanding")
        if baseline_fcf is None or baseline_fcf <= 0:
            missing_inputs.append("free_cash_flow/ufcf (must be positive)")

        if missing_inputs:
            raise ValueError(
                f"Valuation unavailable: Missing or invalid critical financial data for DCF. "
                f"Missing: {', '.join(missing_inputs)}. Details: "
                f"ebit={ebit}, dep={dep}, capex={capex}, wcap={wcap}, cash={cash}, debt={debt}, shares={resolved_shares}, tax_rate={tax_rate}"
            )

        # Resolve FCF CAGR growth rate
        fcf_growth_rate = dcf_inputs.get("fcf_growth_rate")
        fcf_growth_estimated = dcf_inputs.get("fcf_growth_estimated", False)
        fcf_growth_source = dcf_inputs.get("fcf_growth_source")

        if fcf_growth_rate is None:
            if metrics.revenue_growth_yoy is not None:
                fcf_growth_rate = metrics.revenue_growth_yoy / 100.0
                fcf_growth_estimated = True
                fcf_growth_source = "historical revenue CAGR"
            else:
                fcf_growth_rate = 0.08
                fcf_growth_estimated = True
                fcf_growth_source = "default fallback"
        elif not fcf_growth_source:
            fcf_growth_source = "historical FCF CAGR" if not fcf_growth_estimated else "analyst estimate"

        raw_fcf_growth = fcf_growth_rate  # capture before clamping for diagnostics
        from app.services.valuation_utils import clamp_growth_rate
        fcf_growth_rate, growth_was_clamped = clamp_growth_rate(fcf_growth_rate, fcf_growth_source)
        if growth_was_clamped:
            logger.info(
                f"ValuationService: raw growth={raw_fcf_growth:.4%} → clamped to {fcf_growth_rate:.4%} "
                f"(source: {fcf_growth_source}) for {company.company_name if company else 'unknown'}"
            )

        # ── Double-clamp detection ─────────────────────────────────────────────
        valuation_flags: List[str] = []
        double_clamp = check_double_clamp(wacc_was_clamped, growth_was_clamped)
        if double_clamp:
            valuation_flags.append("double_clamp_detected")

        # Call the pure DCF function (same function used by live recommendation)
        (
            intrinsic_share_price,
            projected_fcfs,
            terminal_value,
            enterprise_value,
            equity_value,
        ) = compute_dcf_intrinsic_value(
            baseline_fcf=baseline_fcf,
            fcf_growth_rate=fcf_growth_rate,
            wacc=wacc,
            shares_outstanding=resolved_shares,
            perpetuity_growth_rate=perpetuity_growth_rate,
            cash=cash,
            debt=debt,
        )

        # Calculate PV of forecast flows and PV of terminal value for logging
        pv_of_fcfs_log = sum(fcf_val / ((1 + wacc) ** (idx + 1)) for idx, fcf_val in enumerate(projected_fcfs))
        pv_of_tv_log = terminal_value / ((1 + wacc) ** len(projected_fcfs))

        # Log DB-backed intermediate DCF values
        logger.info(
            f"DB-backed DCF Debug Projections for {company.company_name if company else 'unknown'}:\n"
            f"  Current FCF/UFCF: {baseline_fcf}\n"
            f"  Growth Rate: {fcf_growth_rate}\n"
            f"  WACC: {wacc}\n"
            f"  Terminal Growth: {perpetuity_growth_rate}\n"
            f"  Projected FCFs: {projected_fcfs}\n"
            f"  PV of Forecast Cash Flows: {pv_of_fcfs_log}\n"
            f"  Terminal Value: {terminal_value}\n"
            f"  PV of Terminal Value: {pv_of_tv_log}\n"
            f"  Enterprise Value: {enterprise_value}\n"
            f"  Cash: {cash}\n"
            f"  Debt: {debt}\n"
            f"  Equity Value: {equity_value}\n"
            f"  Shares Outstanding: {resolved_shares}\n"
            f"  Intrinsic Value Per Share: {intrinsic_share_price}"
        )

        actual_growth_g = perpetuity_growth_rate
        if actual_growth_g >= wacc:
            actual_growth_g = wacc - 0.02
            if actual_growth_g < 0.005:
                actual_growth_g = 0.005

        # ── Post-calculation sanity: extreme deviation check ───────────────────
        # Mirrors the 80% deviation check in get_company_recommendation()
        # (company.py router ~L734-751) so both surfaces flag consistently.
        if current_price is not None and current_price > 0:
            deviation = abs(intrinsic_share_price - current_price) / current_price
            if deviation > 0.80:
                double_clamp_note = (
                    " Double-clamp also detected — output is likely an artifact of "
                    "floor/ceiling interaction."
                    if double_clamp else ""
                )
                logger.warning(
                    f"ValuationService: Intrinsic value deviation exceeds 80% for "
                    f"{company.company_name if company else 'unknown'}: "
                    f"Price={current_price}, Intrinsic={intrinsic_share_price}, "
                    f"Deviation={deviation:.2%}. Flagging valuation for review."
                    + double_clamp_note
                )
                valuation_flags.append("extreme_deviation_flagged")

        wacc_details = WaccDetails(
            cost_of_equity=round(cost_of_equity, 4),
            cost_of_debt=round(cost_of_debt, 4),
            equity_weight=round(equity_weight, 4),
            debt_weight=round(debt_weight, 4),
            wacc=round(wacc, 4),
        )

        dcf_details = DcfDetails(
            baseline_fcf=round(baseline_fcf, 2),
            fcf_growth_rate=round(fcf_growth_rate, 4),
            projected_fcfs=projected_fcfs,
            terminal_growth_rate=round(actual_growth_g, 4),
            terminal_value=round(terminal_value, 2),
            enterprise_value=round(enterprise_value, 2),
            equity_value=round(equity_value, 2),
            shares_outstanding=resolved_shares,
            intrinsic_share_price=round(intrinsic_share_price, 2),
        )

        # ── 3. Sensitivity Analysis Grid (5x5) ───────────────────────────────
        # Vary WACC by +/- 0.5%, +/- 1.0%
        # Vary Perpetuity Growth by +/- 0.5%, +/- 1.0%
        wacc_variations = [wacc - 0.01, wacc - 0.005, wacc, wacc + 0.005, wacc + 0.01]
        growth_variations = [
            actual_growth_g - 0.01,
            actual_growth_g - 0.005,
            actual_growth_g,
            actual_growth_g + 0.005,
            actual_growth_g + 0.01
        ]

        sensitivity_grid: List[SensitivityPoint] = []
        for w_var in wacc_variations:
            w_var = max(0.01, w_var)
            for g_var in growth_variations:
                # Perpetual growth must be less than discount rate
                if g_var >= w_var:
                    g_var = w_var - 0.015
                if g_var < 0.001:
                    g_var = 0.001

                tv_var = projected_fcfs[-1] * (1 + g_var) / (w_var - g_var)
                pv_tv_var = tv_var / ((1 + w_var) ** 5)

                pv_fcf_var = 0.0
                for idx, fcf_val in enumerate(projected_fcfs):
                    pv_fcf_var += fcf_val / ((1 + w_var) ** (idx + 1))

                ev_var = pv_fcf_var + pv_tv_var
                eq_var = ev_var + cash - debt
                price_var = eq_var / resolved_shares if resolved_shares > 0 else 0.0

                sensitivity_grid.append(SensitivityPoint(
                    wacc=round(w_var, 4),
                    growth_rate=round(g_var, 4),
                    intrinsic_price=round(price_var, 2)
                ))

        # ── 4. Valuation Confidence Score ─────────────────────────────────────
        fields_present = [
            stmt.revenue is not None,
            stmt.free_cash_flow is not None,
            stmt.shareholders_equity is not None,
            stmt.total_liabilities is not None,
            stmt.ebitda is not None,
            metrics.revenue_growth_yoy is not None,
        ]
        confidence_score = round(sum(fields_present) / len(fields_present), 2)

        logger.bind(
            intrinsic_price=dcf_details.intrinsic_share_price,
            wacc=wacc_details.wacc,
            confidence=confidence_score
        ).info("ValuationService: completed calculations.")

        return ValuationSummary(
            wacc_details=wacc_details,
            dcf_details=dcf_details,
            sensitivity_grid=sensitivity_grid,
            confidence_score=confidence_score,
            beta=round(beta, 2),
            beta_source=beta_source,
            wacc_clamped_due_to_fallback_beta=wacc_clamped_due_to_fallback_beta,
            risk_free_rate=round(risk_free_rate, 4),
            equity_risk_premium=round(erp, 4),
            tax_rate=round(tax_rate, 4),
            cash=round(cash, 2),
            debt=round(debt, 2),
            market_cap=round(market_cap, 2) if market_cap else None,
            cost_of_debt_estimated=cost_of_debt_estimated,
            tax_rate_estimated=tax_rate_estimated,
            fcf_growth_estimated=fcf_growth_estimated,
            as_of=dcf_inputs.get("as_of") or datetime.now(timezone.utc).isoformat().replace("+00:00", "") + "Z",
            currency=dcf_inputs.get("currency") or "USD",
            valuation_flags=valuation_flags,
        )
