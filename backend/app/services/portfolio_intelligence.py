import uuid
from typing import Optional, List, Dict, Any
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.portfolio import PortfolioRepository
from app.services.valuation import ValuationService
from app.services.response_generation import ResponseGenerationService
from app.schemas.portfolio import (
    PortfolioOut, HoldingOut, PortfolioAnalysisResponse,
    PortfolioRecommendationResponse, AllocationItem
)


# Sector risk map to derive portfolio risk scores (1.0 to 10.0 scale)
_SECTOR_RISK_MAP = {
    "technology": 8.0,
    "software": 8.0,
    "semiconductors": 8.5,
    "banking & finance": 5.0,
    "financial": 5.0,
    "energy": 6.0,
    "healthcare": 4.0,
    "pharma": 4.5,
    "automotive": 7.0,
    "retail": 5.5,
    "real estate": 6.5,
    "manufacturing": 5.0,
    "utilities": 3.0,
    "telecom": 4.0,
    "agriculture": 3.5,
}


class PortfolioIntelligenceService:
    """
    PortfolioIntelligenceService handles portfolio valuations, allocation and diversification analysis,
    risk scoring, and AI-generated portfolio recommendations.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PortfolioRepository(db)
        self.valuation_service = ValuationService(db)
        self.response_generator = ResponseGenerationService()

    async def get_portfolio_valuation(self, portfolio_id: uuid.UUID) -> Optional[PortfolioOut]:
        """
        Calculates holdings gains/losses and overall portfolio P&L metrics.
        """
        portfolio = await self.repo.get_portfolio(portfolio_id)
        if not portfolio:
            return None

        holdings_out = []
        total_market_value = 0.0
        total_cost_basis = 0.0

        for holding in portfolio.holdings:
            # 1. Fetch latest intrinsic share price from ValuationService, with 150.0 fallback
            current_price = 150.0
            try:
                val = await self.valuation_service.calculate_valuation(holding.company_id)
                if val and val.dcf_details:
                    current_price = val.dcf_details.intrinsic_share_price
            except Exception as e:
                logger.debug(f"Valuation fallback used for company {holding.company_id}: {e}")

            # 2. Compute P&L
            cost_basis = holding.shares * holding.average_cost
            market_value = holding.shares * current_price
            gain_loss = market_value - cost_basis
            pnl_pct = (gain_loss / cost_basis * 100.0) if cost_basis > 0 else 0.0

            total_market_value += market_value
            total_cost_basis += cost_basis

            holdings_out.append(
                HoldingOut(
                    id=holding.id,
                    company_id=holding.company_id,
                    company_name=holding.company.company_name if holding.company else "Unknown Company",
                    ticker_symbol=holding.company.ticker_symbol if holding.company else "UNK",
                    shares=holding.shares,
                    average_cost=holding.average_cost,
                    current_price=round(current_price, 2),
                    market_value=round(market_value, 2),
                    total_gain_loss=round(gain_loss, 2),
                    pnl_pct=round(pnl_pct, 2)
                )
            )

        total_gain_loss = total_market_value - total_cost_basis
        pnl_pct = (total_gain_loss / total_cost_basis * 100.0) if total_cost_basis > 0 else 0.0

        return PortfolioOut(
            id=portfolio.id,
            name=portfolio.name,
            user_id=portfolio.user_id,
            holdings=holdings_out,
            total_market_value=round(total_market_value, 2),
            total_cost_basis=round(total_cost_basis, 2),
            total_gain_loss=round(total_gain_loss, 2),
            pnl_pct=round(pnl_pct, 2),
            created_at=portfolio.created_at
        )

    async def analyze_portfolio(self, portfolio_id: uuid.UUID) -> Optional[PortfolioAnalysisResponse]:
        """
        Analyzes sector and asset allocations, computes a weighted risk score,
        and determines diversification health.
        """
        val_report = await self.get_portfolio_valuation(portfolio_id)
        if not val_report:
            return None

        total_val = val_report.total_market_value
        if total_val == 0.0:
            return PortfolioAnalysisResponse(
                portfolio_id=portfolio_id,
                portfolio_name=val_report.name,
                total_market_value=0.0,
                allocation_by_company=[],
                allocation_by_sector=[],
                risk_score=5.0,
                diversification_status="Empty Portfolio"
            )

        # 1. Company allocations
        company_allocs = {}
        sector_allocs = {}
        weighted_risk_sum = 0.0

        portfolio = await self.repo.get_portfolio(portfolio_id)

        for idx, h_out in enumerate(val_report.holdings):
            holding_model = portfolio.holdings[idx]
            sector = holding_model.company.sector or "Utilities"
            company_name = h_out.company_name
            pct = (h_out.market_value / total_val) * 100.0

            # Company allocation
            company_allocs[company_name] = company_allocs.get(company_name, 0.0) + pct
            # Sector allocation
            sector_allocs[sector] = sector_allocs.get(sector, 0.0) + pct

            # Risk scoring
            sector_risk = _SECTOR_RISK_MAP.get(sector.lower(), 5.0)
            weighted_risk_sum += sector_risk * (h_out.market_value / total_val)

        # Build allocation lists
        comp_items = [
            AllocationItem(label=k, value=round(total_val * (v / 100.0), 2), percentage=round(v, 2))
            for k, v in company_allocs.items()
        ]
        comp_items.sort(key=lambda x: x.percentage, reverse=True)

        sector_items = [
            AllocationItem(label=k, value=round(total_val * (v / 100.0), 2), percentage=round(v, 2))
            for k, v in sector_allocs.items()
        ]
        sector_items.sort(key=lambda x: x.percentage, reverse=True)

        # 2. Diversification status
        diversification_status = "Well Diversified"
        if any(c.percentage > 40.0 for c in comp_items):
            diversification_status = "Concentrated (High Company Risk)"
        elif any(s.percentage > 50.0 for s in sector_items):
            diversification_status = "Sector Concentrated"

        risk_score = round(weighted_risk_sum, 1) if weighted_risk_sum > 0 else 5.0

        return PortfolioAnalysisResponse(
            portfolio_id=portfolio_id,
            portfolio_name=val_report.name,
            total_market_value=total_val,
            allocation_by_company=comp_items,
            allocation_by_sector=sector_items,
            risk_score=risk_score,
            diversification_status=diversification_status
        )

    async def get_portfolio_recommendations(self, portfolio_id: uuid.UUID) -> Optional[PortfolioRecommendationResponse]:
        """
        Invokes ResponseGenerationService to draft rebalancing recommendations for the portfolio.
        """
        analysis = await self.analyze_portfolio(portfolio_id)
        if not analysis:
            return None

        # Build dynamic context query for the LLM
        query = (
            f"Generate portfolio rebalancing recommendations for portfolio '{analysis.portfolio_name}'. "
            f"Total Value: ${analysis.total_market_value:,.2f}. "
            f"Risk Score: {analysis.risk_score}/10. Diversification: {analysis.diversification_status}. "
            f"Holdings distribution: {', '.join([f'{c.label} ({c.percentage}%)' for c in analysis.allocation_by_company])}. "
            f"Sector distribution: {', '.join([f'{s.label} ({s.percentage}%)' for s in analysis.allocation_by_sector])}. "
            f"Suggest specific allocations adjustments and optimal balance strategy."
        )

        retrieved_chunks = [
            {
                "chunk_text": f"Portfolio analysis context for {analysis.portfolio_name}. Risk level {analysis.risk_score}.",
                "document_title": "Portfolio Context Engine",
                "page_number": 1,
                "section_title": "allocation",
                "similarity_score": 0.99,
            }
        ]

        ai_response = await self.response_generator.generate_response(
            user_query=query,
            company_details=None,
            document_metadata=[],
            retrieved_chunks=retrieved_chunks
        )

        # Generate suggested rebalanced allocations based on current allocations
        suggested_allocs = []
        for s in analysis.allocation_by_sector:
            # Shift towards 15% minimum and maximum 35% to represent suggested rebalancing targets
            target_pct = round(max(15.0, min(35.0, s.percentage)), 2)
            suggested_allocs.append(
                AllocationItem(
                    label=s.label,
                    value=round(analysis.total_market_value * (target_pct / 100.0), 2),
                    percentage=target_pct
                )
            )

        return PortfolioRecommendationResponse(
            portfolio_id=portfolio_id,
            recommendations=ai_response.executive_summary,
            suggested_allocations=suggested_allocs
        )
