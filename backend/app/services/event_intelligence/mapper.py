from typing import Set, Tuple, Dict, List


class IndustryMapper:
    """
    Maps events to directly and indirectly affected industries using a relation propagation graph.
    Designed for relational expansion rather than hardcoded static pairings.
    """
    # Relation propagation weights graph
    INDUSTRY_RELATIONS: Dict[str, Dict[str, float]] = {
        "technology": {"semiconductors": 0.8, "automotive": 0.5, "banking": 0.4},
        "semiconductors": {"technology": 0.9, "automotive": 0.7, "energy": 0.3},
        "automotive": {"semiconductors": 0.6, "energy": 0.5},
        "banking": {"real estate": 0.8, "technology": 0.3},
        "energy": {"automotive": 0.6, "transportation": 0.7},
    }

    @classmethod
    def map_industries(cls, title: str, description: str) -> Tuple[List[str], List[str]]:
        """
        Examines text content to identify directly affected sectors, and uses the propagation
        relations graph to discover indirectly affected sectors.
        Returns:
            Tuple[List[str], List[str]]: (directly_affected, indirectly_affected)
        """
        text = (title + " " + description).lower()
        direct: Set[str] = set()

        # Keyword direct matcher bindings
        if any(k in text for k in ["technology", "software", "cloud", "azure", "windows"]):
            direct.add("technology")
        if any(k in text for k in ["semiconductor", "chip", "foundry", "gpu", "tsmc", "intel"]):
            direct.add("semiconductors")
        if any(k in text for k in ["automotive", "car", "ev", "vehicle", "tesla"]):
            direct.add("automotive")
        if any(k in text for k in ["banking", "finance", "bank", "interest", "credit", "fed"]):
            direct.add("banking")
        if any(k in text for k in ["energy", "oil", "gas", "power", "electricity", "solar"]):
            direct.add("energy")

        # String matching fallback if direct is empty
        if not direct:
            for ind in cls.INDUSTRY_RELATIONS.keys():
                if ind in text:
                    direct.add(ind)

        # Propagate to collect indirect industries
        indirect: Set[str] = set()
        for ind_name in direct:
            relations = cls.INDUSTRY_RELATIONS.get(ind_name, {})
            for rel_name in relations.keys():
                if rel_name not in direct:
                    indirect.add(rel_name)

        return list(direct), list(indirect)
