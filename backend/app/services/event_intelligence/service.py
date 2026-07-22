from datetime import datetime
import time
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.repositories.event import EventRepository
from app.services.base import BaseService
from app.schemas.event import EventAnalyzeResponse, CompanyImpact
from app.models.event import Event, Industry, EventType, EventSeverity

from app.services.event_intelligence.classifier import EventClassifier
from app.services.event_intelligence.mapper import IndustryMapper
from app.services.event_intelligence.matcher import CompanyMatcher
from app.services.event_intelligence.analyzer import ImpactAnalyzer
from app.services.event_intelligence.retriever import EvidenceRetriever


class EventIntelligenceService(BaseService[EventRepository]):
    """
    Orchestration layer coordinates event classification, direct/indirect sector mapping,
    corporate matching, direction analyzes, RAG searches, and DB persistence.
    """
    def __init__(self, db: AsyncSession):
        super().__init__(EventRepository(db))
        self.db = db

    async def analyze(
        self,
        title: str,
        description: str
    ) -> EventAnalyzeResponse:
        """
        Executes complete event analysis and persists records:
        1. Classifies event type and severity.
        2. Discovers directly and indirectly affected industries.
        3. Matches registered companies in database.
        4. Analyzes direction impact + retrieves document evidence.
        5. Saves event data and many-to-many associations in PostgreSQL.
        """
        start_time = time.perf_counter()
        logger.bind(title=title).info("Starting Event Intelligence analysis pipeline.")

        # Classify event
        event_type, severity = EventClassifier.classify(title, description)

        # Map affected industries
        direct_ind, indirect_ind = IndustryMapper.map_industries(title, description)
        all_affected_industries = list(set(direct_ind + indirect_ind))

        # Find companies operating in affected industries
        matcher = CompanyMatcher(self.db)
        matched_companies = await matcher.match_companies(
            direct_industries=direct_ind,
            indirect_industries=indirect_ind,
            event_title=title,
            event_description=description
        )

        # Build impact profile + retrieve RAG chunk evidence
        retriever = EvidenceRetriever(self.db)
        potentially_impacted_companies = []

        for item in matched_companies:
            company = item["company"]
            confidence = item["confidence_score"]

            # Analyze impact direction
            impact_info = ImpactAnalyzer.analyze_impact(
                company_name=company.company_name,
                industry=company.industry,
                event_title=title,
                event_description=description
            )

            # Retrieve evidence chunks from RAG pipeline
            evidence = await retriever.retrieve_evidence(
                company_id=company.id,
                query=f"{title} {description}",
                top_k=2
            )

            potentially_impacted_companies.append(
                CompanyImpact(
                    company_id=company.id,
                    company_name=company.company_name,
                    industry=company.industry,
                    impact_type=impact_info["impact_type"],
                    confidence_score=confidence,
                    reasoning=impact_info["reasoning"],
                    evidence=evidence
                )
            )

        # Persist Event metadata and industry mapping
        db_industries = []
        for ind_name in all_affected_industries:
            ind_obj = await self.repository.get_or_create_industry(ind_name)
            db_industries.append(ind_obj)

        db_event = Event(
            title=title,
            description=description,
            event_type=event_type,
            severity=severity,
            event_date=datetime.utcnow(),
            industries=db_industries
        )

        self.db.add(db_event)
        await self.db.commit()

        # Telemetry Logging
        duration = time.perf_counter() - start_time
        logger.bind(
            event_type=event_type.value,
            severity=severity.value,
            affected_industries=all_affected_industries,
            impacted_companies=[c.company_name for c in potentially_impacted_companies],
            confidence_scores=[c.confidence_score for c in potentially_impacted_companies],
            retrieved_evidence_count=sum(len(c.evidence) for c in potentially_impacted_companies),
            duration_seconds=duration
        ).info("Event Intelligence analysis completed.")

        return EventAnalyzeResponse(
            event_summary=description[:200] + "..." if len(description) > 200 else description,
            event_type=event_type.value,
            severity=severity.value,
            affected_industries=all_affected_industries,
            potentially_impacted_companies=potentially_impacted_companies
        )
