from typing import Dict, Optional, Tuple
from enum import Enum
from loguru import logger


class MissingReason(str, Enum):
    NOT_REPORTED = "NOT_REPORTED"          # Field confirmed absent from filings
    NOT_APPLICABLE = "NOT_APPLICABLE"      # Field logically doesn't apply
    UNABLE_TO_EXTRACT = "UNABLE_TO_EXTRACT"  # Parsing failed / ambiguous data


class FinancialValidator:
    """
    Validates normalized financial values before persistence.
    Classifies invalid or missing values with explicit sentinel reasons.
    """

    # Fields that must not be negative (business logic constraints)
    NON_NEGATIVE_FIELDS = {"revenue", "total_assets", "total_liabilities"}
    # Fields required for basic metric calculation
    REQUIRED_FOR_METRICS = {"revenue", "net_profit", "total_assets"}

    @classmethod
    def validate(
        cls,
        normalized_fields: Dict[str, Optional[float]]
    ) -> Tuple[Dict[str, Optional[float]], Dict[str, MissingReason]]:
        """
        Validates all financial fields.

        Returns:
            clean_values: dict of field → float (None for invalid/missing)
            missing_reasons: dict of field → MissingReason sentinel for every None field
        """
        clean_values: Dict[str, Optional[float]] = {}
        missing_reasons: Dict[str, MissingReason] = {}

        for field, value in normalized_fields.items():
            if value is None:
                missing_reasons[field] = MissingReason.UNABLE_TO_EXTRACT
                clean_values[field] = None
                logger.debug(f"Validator: '{field}' = UNABLE_TO_EXTRACT")

            elif field in cls.NON_NEGATIVE_FIELDS and value < 0:
                logger.warning(f"Validator: '{field}' = {value} is negative — expected non-negative. Marking NOT_REPORTED.")
                missing_reasons[field] = MissingReason.NOT_REPORTED
                clean_values[field] = None

            else:
                clean_values[field] = value

        # Cross-field check: if total_assets exists but shareholders_equity is missing,
        # attempt to derive it: equity = assets - liabilities
        if (
            clean_values.get("total_assets") is not None
            and clean_values.get("total_liabilities") is not None
            and clean_values.get("shareholders_equity") is None
        ):
            derived = clean_values["total_assets"] - clean_values["total_liabilities"]
            clean_values["shareholders_equity"] = derived
            missing_reasons.pop("shareholders_equity", None)
            logger.info(f"Validator: derived shareholders_equity = {derived} from assets - liabilities.")

        return clean_values, missing_reasons
