"""
Core utility functions for FinIQ backend.
"""
from typing import Optional, Union
import re


def normalize_fiscal_year(fy_input: Optional[Union[int, str]]) -> int:
    """
    Normalizes any fiscal year representation (int, str, '26', 'FY26', 'FY2026', '2026')
    to a canonical 4-digit integer (e.g. 2026).

    Examples
    --------
    >>> normalize_fiscal_year(2026)
    2026
    >>> normalize_fiscal_year("2025")
    2025
    >>> normalize_fiscal_year("26")
    2026
    >>> normalize_fiscal_year("FY26")
    2026
    >>> normalize_fiscal_year("FY2025")
    2025
    """
    if fy_input is None:
        return 2026

    if isinstance(fy_input, int):
        if fy_input < 100:
            return 2000 + fy_input
        return fy_input

    s = str(fy_input).strip().upper()
    digits = re.findall(r"\d+", s)
    if not digits:
        return 2026

    val = int(digits[0])
    if val < 100:
        return 2000 + val
    return val
