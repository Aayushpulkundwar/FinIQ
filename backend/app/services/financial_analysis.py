import uuid
from decimal import Decimal
from typing import List, Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.company import Company
from app.models.financial import FinancialPeriod, FinancialStatement, FinancialMetric


class FinancialIntelligenceEngine:
    """
    Engine performing programmatic calculations for valuations, growth, scenario modeling, 
    and structured database lookups of company financial profiles.
    """
    
    @staticmethod
    def calculate_dcf(
        fcf: float,
        growth_rate: float,  # e.g., 0.10 for 10%
        discount_rate: float,  # e.g., 0.12 for 12%
        terminal_growth: float = 0.03,  # e.g., 3%
        periods: int = 5
    ) -> Dict[str, Any]:
        """
        Calculates Discounted Cash Flow valuation.
        """
        projected_fcf = []
        present_values = []
        
        current_fcf = fcf
        for t in range(1, periods + 1):
            current_fcf = current_fcf * (1 + growth_rate)
            projected_fcf.append(current_fcf)
            pv = current_fcf / ((1 + discount_rate) ** t)
            present_values.append(pv)
            
        # Terminal Value
        terminal_fcf = projected_fcf[-1] * (1 + terminal_growth)
        terminal_value = terminal_fcf / (discount_rate - terminal_growth)
        pv_terminal_value = terminal_value / ((1 + discount_rate) ** periods)
        
        enterprise_value = sum(present_values) + pv_terminal_value
        
        return {
            "projected_fcf": projected_fcf,
            "present_values": present_values,
            "terminal_value": terminal_value,
            "pv_terminal_value": pv_terminal_value,
            "enterprise_value": enterprise_value,
            "parameters": {
                "initial_fcf": fcf,
                "growth_rate": growth_rate,
                "discount_rate": discount_rate,
                "terminal_growth": terminal_growth,
                "periods": periods
            }
        }

    @staticmethod
    def calculate_yoy_growth(values: List[float]) -> List[float]:
        """
        Calculates Year-over-Year growth rates.
        """
        growth_rates = []
        for i in range(1, len(values)):
            prev = values[i-1]
            curr = values[i]
            if prev != 0:
                growth_rates.append((curr - prev) / prev)
            else:
                growth_rates.append(0.0)
        return growth_rates

    @staticmethod
    def calculate_margins(revenue: float, ebitda: float, net_profit: float) -> Dict[str, float]:
        """
        Calculates EBITDA and Net Profit margins.
        """
        return {
            "ebitda_margin": ebitda / revenue if revenue != 0 else 0.0,
            "net_profit_margin": net_profit / revenue if revenue != 0 else 0.0
        }

    @staticmethod
    def generate_scenarios(
        base_fcf: float,
        growth_base: float = 0.08,
        growth_bull: float = 0.15,
        growth_bear: float = 0.02,
        discount_rate: float = 0.10,
        terminal_growth: float = 0.03
    ) -> Dict[str, Dict[str, Any]]:
        """
        Generates DCF valuations for Bull, Base, and Bear scenarios.
        """
        return {
            "bull": FinancialIntelligenceEngine.calculate_dcf(base_fcf, growth_bull, discount_rate, terminal_growth),
            "base": FinancialIntelligenceEngine.calculate_dcf(base_fcf, growth_base, discount_rate, terminal_growth),
            "bear": FinancialIntelligenceEngine.calculate_dcf(base_fcf, growth_bear, discount_rate, terminal_growth),
        }

    @staticmethod
    async def get_company_financials(db: Any, company_id: uuid.UUID) -> List[Dict[str, Any]]:
        """
        Retrieves historical financial statements and metrics for a company, sorted by year.
        """
        stmt = (
            select(FinancialPeriod)
            .filter(FinancialPeriod.company_id == company_id)
            .options(
                selectinload(FinancialPeriod.statements).selectinload(FinancialStatement.metrics)
            )
            .order_by(FinancialPeriod.fiscal_year.asc())
        )
        res = await db.execute(stmt)
        periods = res.scalars().all()
        
        financials = []
        for period in periods:
            for statement in period.statements:
                metric_data = {}
                if statement.metrics:
                    metric = statement.metrics[0]
                    metric_data = {
                        "revenue_growth_yoy": float(metric.revenue_growth_yoy) if metric.revenue_growth_yoy else None,
                        "ebitda_margin": float(metric.ebitda_margin) if metric.ebitda_margin else None,
                        "net_profit_margin": float(metric.net_profit_margin) if metric.net_profit_margin else None,
                        "roe": float(metric.roe) if metric.roe else None,
                        "roce": float(metric.roce) if metric.roce else None,
                        "debt_to_equity": float(metric.debt_to_equity) if metric.debt_to_equity else None,
                        "current_ratio": float(metric.current_ratio) if metric.current_ratio else None,
                        "free_cash_flow_yield": float(metric.free_cash_flow_yield) if metric.free_cash_flow_yield else None,
                    }
                
                financials.append({
                    "fiscal_year": period.fiscal_year,
                    "period_type": period.period_type.value,
                    "currency": period.currency,
                    "revenue": float(statement.revenue) if statement.revenue else None,
                    "ebitda": float(statement.ebitda) if statement.ebitda else None,
                    "operating_income": float(statement.operating_income) if statement.operating_income else None,
                    "net_profit": float(statement.net_profit) if statement.net_profit else None,
                    "eps": float(statement.eps) if statement.eps else None,
                    "total_assets": float(statement.total_assets) if statement.total_assets else None,
                    "total_liabilities": float(statement.total_liabilities) if statement.total_liabilities else None,
                    "shareholders_equity": float(statement.shareholders_equity) if statement.shareholders_equity else None,
                    "operating_cash_flow": float(statement.operating_cash_flow) if statement.operating_cash_flow else None,
                    "free_cash_flow": float(statement.free_cash_flow) if statement.free_cash_flow else None,
                    "capex": float(statement.capex) if statement.capex else None,
                    "metrics": metric_data
                })
        return financials

    @staticmethod
    async def get_peer_comparison(db: Any, company_id: uuid.UUID) -> Dict[str, Any]:
        """
        Performs comparative metrics lookup against company's specified peers.
        """
        # Fetch target company
        comp_stmt = select(Company).filter(Company.id == company_id)
        comp_res = await db.execute(comp_stmt)
        target_company = comp_res.scalars().first()
        if not target_company:
            return {}

        comparison = {
            "target": {
                "name": target_company.company_name,
                "ticker": target_company.ticker_symbol,
                "financials": await FinancialIntelligenceEngine.get_company_financials(db, company_id)
            },
            "peers": []
        }

        # Fetch peers
        if target_company.peer_tickers:
            peer_tickers = [t.strip().upper() for t in target_company.peer_tickers.split(",") if t.strip()]
            for ticker in peer_tickers:
                peer_stmt = select(Company).filter(Company.ticker_symbol == ticker)
                peer_res = await db.execute(peer_stmt)
                peer_comp = peer_res.scalars().first()
                if peer_comp:
                    comparison["peers"].append({
                        "name": peer_comp.company_name,
                        "ticker": peer_comp.ticker_symbol,
                        "financials": await FinancialIntelligenceEngine.get_company_financials(db, peer_comp.id)
                    })
        return comparison
