import re
from typing import Optional
from loguru import logger

# Unit scale multipliers (normalized to base currency units)
UNIT_MULTIPLIERS = {
    "billion": 1_000_000_000,
    "bn":      1_000_000_000,
    "million": 1_000_000,
    "mn":      1_000_000,
    "mn.":     1_000_000,
    "crore":   10_000_000,
    "cr":      10_000_000,
    "lakh":    100_000,
    "thousand":1_000,
    "k":       1_000,
    "tr":      1_000_000_000_000,
    "trillion":1_000_000_000_000,
}

# Regex to detect parenthetical negative values like (1,234.5)
PARENTHETICAL_NEGATIVE = re.compile(r"^\(([0-9,\.]+)\)$")


class FinancialNormalizer:
    """
    Normalizes raw extracted string values to numeric floats.
    Handles unit scaling (millions/billions/crores), currency stripping,
    and parenthetical negative number conventions.
    """

    @staticmethod
    def normalize(raw_value: any) -> Optional[float]:
        """
        Converts a raw extracted string to a normalized float, or returns a numeric as-is.
        Returns None if value cannot be parsed.
        """
        if raw_value is None:
            return None

        if isinstance(raw_value, (int, float)):
            return float(raw_value)

        raw = str(raw_value).strip()

        # Check for parenthetical negative: (1,234.5)
        paren_match = PARENTHETICAL_NEGATIVE.match(raw)
        sign = 1.0
        if paren_match:
            raw = paren_match.group(1)
            sign = -1.0

        # Strip currency symbols
        raw = re.sub(r"[\$₹€£¥₩]", "", raw).strip()

        # Detect unit multiplier
        multiplier = 1.0
        lower = raw.lower()
        for unit_key, unit_val in sorted(UNIT_MULTIPLIERS.items(), key=lambda x: -len(x[0])):
            if lower.endswith(unit_key):
                multiplier = float(unit_val)
                raw = raw[:len(raw) - len(unit_key)].strip()
                break

        # Strip commas and parse numeric
        raw = raw.replace(",", "").strip()

        try:
            value = float(raw) * multiplier * sign
            return round(value, 4)
        except (ValueError, TypeError):
            logger.warning(f"FinancialNormalizer: could not parse '{raw_value}' as float.")
            return None

    @classmethod
    def normalize_all(cls, parsed_fields: dict) -> dict:
        """
        Normalizes an entire dict of field_name → raw_string_value or numeric.
        Returns dict of field_name → normalized float | None.
        """
        return {
            field: cls.normalize(raw)
            for field, raw in parsed_fields.items()
        }
