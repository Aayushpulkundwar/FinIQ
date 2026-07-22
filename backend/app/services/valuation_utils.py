from typing import Any, Optional
from loguru import logger

WACC_MIN = 0.06
WACC_MAX = 0.15
GROWTH_MIN = -0.15
GROWTH_MAX = 0.25

def clamp_wacc(raw_wacc: float) -> tuple[float, bool]:
    """
    Clamps WACC to WACC_MIN and WACC_MAX.
    Returns (clamped_wacc, was_clamped)
    """
    clamped = max(WACC_MIN, min(WACC_MAX, raw_wacc))
    was_clamped = (clamped != raw_wacc)
    if was_clamped:
        logger.warning(
            f"CRITICAL SANITY CHECK: Raw computed WACC {raw_wacc:.2%} is outside typical range "
            f"({WACC_MIN:.1%} to {WACC_MAX:.1%}). Clamping to {clamped:.2%}."
        )
    return clamped, was_clamped

def clamp_growth_rate(raw_growth: float, source: str = "unknown") -> tuple[float, bool]:
    """
    Clamps FCF growth rate to GROWTH_MIN and GROWTH_MAX.
    Returns (clamped_growth, was_clamped)
    """
    clamped = max(GROWTH_MIN, min(GROWTH_MAX, raw_growth))
    was_clamped = (clamped != raw_growth)
    if was_clamped:
        logger.warning(
            f"CRITICAL SANITY CHECK: Growth rate {raw_growth:.2%} (source: {source}) is outside typical range "
            f"({GROWTH_MIN:.1%} to {GROWTH_MAX:.1%}). Clamping to {clamped:.2%} for projections."
        )
    else:
        logger.info(
            f"DCF Projections: Using growth rate {clamped:.2%} (source: {source})."
        )
    return clamped, was_clamped


def check_double_clamp(wacc_was_clamped: bool, growth_was_clamped: bool) -> bool:
    """
    Returns True if BOTH WACC and FCF growth rate were simultaneously clamped.

    A simultaneous floor-hit interaction (e.g. WACC clamped to 6% floor AND growth
    clamped to -15% floor) can produce extreme/misleading DCF outputs that are
    artifacts of the bound interaction, not genuine market signals.

    Callers should append "double_clamp_detected" to their valuation_flags list
    when this returns True, and surface that flag in the API response so consumers
    understand why the number looks extreme.
    """
    if wacc_was_clamped and growth_was_clamped:
        logger.warning(
            "DOUBLE-CLAMP DETECTED: Both WACC and FCF growth rate were simultaneously "
            "driven to their clamped bounds. The resulting DCF output may be an artifact "
            "of the floor/ceiling interaction rather than a genuine valuation signal. "
            "Flagging result as 'double_clamp_detected'."
        )
        return True
    return False


def get_sector_fallback_beta(sector: Optional[str]) -> float:
    """
    Returns the sector-average fallback beta.
    Uses the existing sector mappings in the codebase.
    """
    if sector:
        sector_lower = sector.lower()
        if "tech" in sector_lower or "software" in sector_lower:
            return 1.25
        elif "utility" in sector_lower or "utilities" in sector_lower:
            return 0.75
        elif "financial" in sector_lower or "bank" in sector_lower:
            return 1.1
    return 1.0


def validate_beta(raw_beta: Any, sector: Optional[str]) -> tuple[float, str]:
    """
    Validates beta value against the sane range of [0.2, 3.0].
    If raw_beta is None, non-numeric, or outside range, falls back to the sector-average.
    Returns (beta, beta_source)
    """
    if raw_beta is None:
        return get_sector_fallback_beta(sector), "fallback_api_none"

    try:
        val = float(raw_beta)
    except (TypeError, ValueError):
        return get_sector_fallback_beta(sector), "fallback_type_error"

    if val < 0.2 or val > 3.0:
        return get_sector_fallback_beta(sector), "fallback_invalid_range"

    return val, "yfinance_valid"


def clamp_wacc_with_beta_check(raw_wacc: float, beta_source: str) -> tuple[float, bool, bool]:
    """
    Clamps WACC and flags whether clamping was due to a fallback beta.
    Returns (clamped_wacc, was_clamped, wacc_clamped_due_to_fallback_beta)
    """
    clamped, was_clamped = clamp_wacc(raw_wacc)
    wacc_clamped_due_to_fallback_beta = was_clamped and (beta_source != "yfinance_valid")
    return clamped, was_clamped, wacc_clamped_due_to_fallback_beta

