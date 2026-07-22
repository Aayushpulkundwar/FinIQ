from typing import Dict, Any


class ImpactAnalyzer:
    """
    Analyzes event text against company profiles to determine impact direction (Positive, Negative, Neutral)
    and writes explainable rationale.
    """
    @staticmethod
    def analyze_impact(
        company_name: str,
        industry: str,
        event_title: str,
        event_description: str
    ) -> Dict[str, str]:
        """
        Determines impact metrics.
        Returns:
            Dict[str, str]: carrying "impact_type" and "reasoning".
        """
        text = (event_title + " " + event_description).lower()

        positive_keywords = ["subsidy", "subsidies", "grant", "growth", "expansion", "merger", "alliance", "rate cut", "easing"]
        negative_keywords = ["tariff", "fine", "sanction", "lawsuit", "shortage", "investigation", "antitrust", "ban", "crisis", "inflation", "tax increase"]

        # Evaluate impact direction
        is_positive = any(k in text for k in positive_keywords)
        is_negative = any(k in text for k in negative_keywords)

        if is_positive and not is_negative:
            impact_type = "Positive Impact"
            reasoning = (
                f"The event highlights market catalysts (such as tax subsidies, rate cuts, or expansion alignments) "
                f"which presents a Positive Impact for {company_name} in the {industry} sector."
            )
        elif is_negative:
            impact_type = "Negative Impact"
            reasoning = (
                f"The event introduces macro/regulatory headwinds (such as tariffs, antitrust lawsuits, or shortages) "
                f"posing a Negative Impact for {company_name}."
            )
        else:
            impact_type = "Neutral Impact"
            reasoning = (
                f"The event presents general industry/market conditions which represents a Neutral Impact "
                f"on {company_name}'s core business operations at this time."
            )

        return {
            "impact_type": impact_type,
            "reasoning": reasoning
        }
