import re
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.company import CompanyRepository


class CompanyMatcher:
    """
    Queries database corporate records matching affected industries and evaluates confidence scores.
    Confidence scores are weighted by industry mapping types and ticker/name occurrences.
    """
    def __init__(self, db: AsyncSession):
        self.repo = CompanyRepository(db)

    async def match_companies(
        self,
        direct_industries: List[str],
        indirect_industries: List[str],
        event_title: str,
        event_description: str,
    ) -> List[Dict[str, Any]]:
        """
        Queries companies and assigns confidence scores.
        Returns:
            List[Dict[str, Any]]: List of dicts carrying "company" object and "confidence_score".
        """
        # Fetch registered companies
        companies = await self.repo.get_multi(skip=0, limit=100)

        matched = []
        text = (event_title + " " + event_description).lower()

        for company in companies:
            comp_industry = company.industry.lower()
            confidence = 0.0

            # 1. Match direct industry categories
            if comp_industry in [d.lower() for d in direct_industries]:
                confidence = 0.9
            # 2. Match indirect industry categories
            elif comp_industry in [i.lower() for i in indirect_industries]:
                confidence = 0.6

            # 3. Elevate confidence if corporate ticker or name is explicitly mentioned in event text
            if company.ticker_symbol.lower() in text or company.company_name.lower() in text:
                confidence = max(confidence, 0.95)

            if confidence > 0.0:
                matched.append({
                    "company": company,
                    "confidence_score": confidence
                })

        return matched
