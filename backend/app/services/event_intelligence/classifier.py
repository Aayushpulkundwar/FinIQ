import re
from typing import Tuple
from app.models.event import EventType, EventSeverity


class EventClassifier:
    """
    Categorizes incoming corporate or market events into standard classifications and severities.
    Uses descriptive query keyword rules to operate deterministically offline.
    """
    @staticmethod
    def classify(title: str, description: str) -> Tuple[EventType, EventSeverity]:
        text = (title + " " + description).lower()

        # Classify Event Type — order matters: more specific patterns first
        if any(k in text for k in ["interest rate", "inflation", "gdp", "unemployment", "fed", "macroeconomic", "recession", "macro"]):
            event_type = EventType.macroeconomic
        elif any(k in text for k in ["geopolitical", "war", "conflict", "sanction", "export control", "military"]):
            event_type = EventType.geopolitical
        elif any(k in text for k in ["regulation", "sec", "compliance", "fine", "lawsuit", "antitrust", "ftc", "audit", "regulatory"]):
            event_type = EventType.regulatory
        elif any(k in text for k in ["policy", "election", "government", "tariff", "trade war", "subsidies"]):
            event_type = EventType.policy
        elif any(k in text for k in ["semiconductor", "automotive", "banking", "tech sector", "industry transition", "sector"]):
            event_type = EventType.industry
        else:
            event_type = EventType.company_specific

        # Classify Event Severity
        if any(k in text for k in ["critical", "collapse", "crisis", "shutdown", "sanctions", "antitrust lawsuit", "bankruptcy", "crash"]):
            severity = EventSeverity.CRITICAL
        elif any(k in text for k in ["high", "rate hike", "tariff increase", "investigation", "imposition", "ban", "shortage"]):
            severity = EventSeverity.HIGH
        elif any(k in text for k in ["medium", "merger", "policy update", "regulation change"]):
            severity = EventSeverity.MEDIUM
        else:
            severity = EventSeverity.LOW

        return event_type, severity
