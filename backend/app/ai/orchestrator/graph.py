import time
import re
import json
from typing import List, Dict, Any, Optional
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.ai.orchestrator.state import AgentState
from app.ai.orchestrator.tools import create_tools


class ExtendedAgentState(AgentState):
    """
    AgentState extension adding transient plan routing values and final context storage.
    """
    planned_tools: List[Dict[str, Any]]
    planned_agents: List[str]
    agent_outputs: Dict[str, Any]


# Tool to Agent mapping
TOOL_TO_AGENT = {
    "get_company_by_ticker": "company_analysis",
    "list_companies": "company_analysis",
    "list_documents": "company_analysis",
    "get_document_metadata": "company_analysis",
    "analyze_financial_intelligence": "financial_statement",
    "analyze_market_intelligence": "news_intelligence",
    "analyze_event_intelligence": "event_intelligence",
    "calculate_company_valuation": "valuation",
    "search_knowledge": "risk_analysis",
    "generate_research_report": "report_generation"
}


# ── Routing Helper ────────────────────────────────────────────────────────────

def route_next_agent(state: ExtendedAgentState) -> str:
    """Router helper checking which planned agent to invoke next."""
    planned = state.get("planned_agents", [])
    history = state.get("execution_history", [])
    
    for agent in planned:
        if agent not in history:
            logger.info(f"Router: next agent is '{agent}'")
            return agent
            
    logger.info("Router: all planned agents complete. Routing to 'report_generation'")
    return "report_generation"


# ── Supervisor Node ───────────────────────────────────────────────────────────

async def supervisor_node(state: ExtendedAgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Supervisor Node: Analyzes user query, decides which tools to invoke,
    maps them to agent assignments, and schedules execution.
    """
    query = state.get("user_query", "")
    logger.bind(query=query).info("Supervisor node analyzing query routing.")

    planned: List[Dict[str, Any]] = []
    routed_successfully = False

    openrouter_key = settings.OPENROUTER_API_KEY
    if openrouter_key and "placeholder" not in (openrouter_key or "").lower():
        try:
            from app.core.openrouter_client import openrouter_chat
            # Cap query to 2000 chars as a generous safety limit for routing prompts
            query_for_routing = query[:2000]
            routing_system_prompt = (
                "You are the Supervisor Router for FinsightAI. Determine which tools are needed "
                f"to answer this query: '{query_for_routing}'. You must return ONLY a JSON list of tool calls. "
                "Each tool call must be an object with keys 'name' and 'args'.\n"
                "Available tools:\n"
                "1. get_company_by_ticker (args: ticker_symbol)\n"
                "2. list_companies (args: {})\n"
                "3. search_knowledge (args: query, company_id) - USE THIS as the DEFAULT for general Q&A, product information, business overview, strategy, R&D initiatives, partnerships, collaborations (e.g. H&M), future products, product pipeline, upcoming launches, Chairman's message, ESG, sustainability, and any query that retrieves facts from company documents\n"
                "4. list_documents (args: company_id)\n"
                "5. get_document_metadata (args: document_id)\n"
                "6. analyze_event_intelligence (args: title, description) - USE ONLY for broad external events: regulatory changes, macroeconomic shifts, geopolitical events, industry-wide disruptions. Do NOT use for company-specific product or partnership questions\n"
                "7. analyze_financial_intelligence (args: company_id, fiscal_year, period_type) - USE for financial analysis, earnings, revenue, margins, balance sheet, cash flow, ratio, and financial performance queries\n"
                "8. calculate_company_valuation (args: company_id, fiscal_year) - USE for DCF, WACC, intrinsic share price estimation, and sensitivity grids\n"
                "9. generate_research_report (args: company_id, fiscal_year) - USE for comprehensive investment research reports\n"
                "10. analyze_market_intelligence (args: company_id, industry, limit) - USE for market news, headlines, market update, sentiment, and market intelligence queries\n\n"
                "IMPORTANT: When in doubt, prefer search_knowledge. Only use specialized tools (7-10) when the query explicitly asks for financial figures, valuations, market news, or full research reports.\n\n"
                "Example response:\n"
                '[{"name": "get_company_by_ticker", "args": {"ticker_symbol": "MSFT"}}, '
                '{"name": "search_knowledge", "args": {"query": "revenue metrics"}}]'
            )
            logger.info(
                f"SupervisorNode: LLM routing invocation started "
                f"(model={settings.OPENROUTER_MODEL}, full JSON prompt)."
            )
            llm_result = await openrouter_chat(
                messages=[
                    {"role": "system", "content": routing_system_prompt},
                    {"role": "user", "content": query_for_routing},
                ],
                model=settings.OPENROUTER_MODEL,
                api_key=openrouter_key,
                base_url=settings.OPENROUTER_BASE_URL,
                caller_label="SupervisorNode.route",
            )
            logger.info(
                f"SupervisorNode: Routing response from provider={llm_result.provider_used}."
            )
            cleaned_routing = llm_result.content.strip()
            if cleaned_routing.startswith("```"):
                cleaned_routing = re.sub(r"^```json\s*|```$", "", cleaned_routing, flags=re.MULTILINE).strip()

            # ---------------------------------------------------------------
            # JSON schema validation before trusting routing output.
            # Must be: a non-empty list of dicts, each with 'name' and 'args'.
            # If validation fails, fall through to keyword router.
            # ---------------------------------------------------------------
            try:
                candidate = json.loads(cleaned_routing)
            except (json.JSONDecodeError, ValueError) as parse_err:
                logger.warning(
                    f"SupervisorNode: LLM routing output from "
                    f"provider={llm_result.provider_used} is not valid JSON "
                    f"({parse_err}). Falling back to keyword router."
                )
                candidate = None

            if candidate is not None:
                if (
                    isinstance(candidate, list)
                    and len(candidate) > 0
                    and all(
                        isinstance(item, dict) and "name" in item and "args" in item
                        for item in candidate
                    )
                ):
                    planned = candidate
                    logger.info(
                        f"SupervisorNode: Routing validation passed — tools: {planned}"
                    )
                    routed_successfully = True
                else:
                    logger.warning(
                        f"SupervisorNode: LLM routing output from "
                        f"provider={llm_result.provider_used} failed schema validation "
                        f"(expected list of {{name, args}}). Falling back to keyword router. "
                        f"Got: {str(candidate)[:200]}"
                    )

        except Exception as openrouter_route_err:
            logger.warning(
                f"SupervisorNode: LLM routing failed: {openrouter_route_err}."
            )


    is_placeholder = not routed_successfully

    if is_placeholder:
        # Rule-based / Fallback Router Path
        logger.info("Using deterministic rule-based router.")
        event_keywords = [
            "event", "impact", "macroeconomic", "geopolitical", "regulatory", "policy",
            "rate hike", "interest rate", "inflation", "tariff", "sanction", "recession",
            "regulation", "legislation", "antitrust", "sector disruption", "industry crisis"
        ]
        financial_keywords = [
            "revenue", "ebitda", "income statement", "balance sheet", "cash flow",
            "earnings", "margin", "profit", "eps", "financial", "ratio", "roe",
            "roce", "debt", "equity", "assets", "liabilities", "capex", "free cash flow",
            "net income", "quarterly results", "annual results", "financials"
        ]
        valuation_keywords = ["valuation", "dcf", "wacc", "intrinsic", "discounted cash", "sensitivity"]
        report_keywords = ["research report", "investment report", "report generator", "analyst report"]
        market_keywords = [
            "market news", "market update", "market intelligence", "market sentiment",
            "news headline", "market summary", "financial news", "latest news",
            "news analysis", "market outlook", "market trends",
        ]

        # NOTE: Known Limitation - Coreference Resolution
        # Follow-up queries without explicit company names or tickers (e.g. "what is its valuation?")
        # will not trigger company resolution here. We fall back to rule-based routing or search without
        # resolving company context from the active session's conversation history.
        tickers = re.findall(r"\b[A-Z]{2,5}\b", query)
        has_ticker = len(tickers) > 0

        def matches_any_keyword(text: str, keywords: List[str]) -> bool:
            text_lower = text.lower()
            for k in keywords:
                pattern = r"\b" + re.escape(k) + r"\b"
                if re.search(pattern, text_lower):
                    return True
            return False

        if matches_any_keyword(query, report_keywords):
            if has_ticker:
                planned.append({"name": "get_company_by_ticker", "args": {"ticker_symbol": tickers[0]}})
            planned.append({
                "name": "generate_research_report",
                "args": {"company_id": "__resolve_from_ticker__"}
            })
        elif matches_any_keyword(query, valuation_keywords):
            if has_ticker:
                planned.append({"name": "get_company_by_ticker", "args": {"ticker_symbol": tickers[0]}})
            planned.append({
                "name": "calculate_company_valuation",
                "args": {"company_id": "__resolve_from_ticker__"}
            })
        elif matches_any_keyword(query, financial_keywords):
            if has_ticker:
                for ticker in tickers[:1]:
                    planned.append({"name": "get_company_by_ticker", "args": {"ticker_symbol": ticker}})
            planned.append({
                "name": "analyze_financial_intelligence",
                "args": {"company_id": "__resolve_from_ticker__"}
            })
        elif matches_any_keyword(query, event_keywords):
            planned.append({
                "name": "analyze_event_intelligence",
                "args": {"title": query[:255], "description": query}
            })
        elif matches_any_keyword(query, market_keywords):
            industry_hint = None
            for ind in ["tech", "banking", "energy", "pharma", "auto", "retail", "telecom"]:
                if matches_any_keyword(query, [ind]):
                    industry_hint = ind
                    break
            planned.append({
                "name": "analyze_market_intelligence",
                "args": {"industry": industry_hint, "limit": 20}
            })
        else:
            for ticker in tickers:
                planned.append({"name": "get_company_by_ticker", "args": {"ticker_symbol": ticker}})
            if "list companies" in query.lower() or "all companies" in query.lower():
                planned.append({"name": "list_companies", "args": {}})
            if "document" in query.lower() or "report" in query.lower():
                planned.append({"name": "list_documents", "args": {}})
            search_args = {"query": query}
            if has_ticker:
                search_args["company_id"] = "__resolve_from_ticker__"
            planned.append({"name": "search_knowledge", "args": search_args})

    # Derive planned agents from tools
    planned_agents = []
    for tc in planned:
        agent = TOOL_TO_AGENT.get(tc.get("name"))
        if agent and agent not in planned_agents:
            planned_agents.append(agent)

    logger.info(f"Planned agents for query: {planned_agents}")

    return {
        "planned_tools": planned,
        "planned_agents": planned_agents,
        "agent_outputs": {},
        "execution_history": []
    }


# ── Generic Agent Node Executor Helper ────────────────────────────────────────

async def execute_agent_node(agent_name: str, state: ExtendedAgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Helper method to run all planned tools assigned to a specific agent name."""
    db: AsyncSession = config.get("configurable", {}).get("db")
    if not db:
        raise ValueError("Database session was not found in config.")

    tools = create_tools(db)
    planned = state.get("planned_tools", [])
    history = list(state.get("execution_history", []))
    agent_outputs = dict(state.get("agent_outputs", {}))

    retrieved_chunks = list(state.get("retrieved_chunks", []))
    company_details = state.get("company_details")
    document_metadata = list(state.get("document_metadata", []))

    logger.info(f"Agent '{agent_name}' starting execution.")

    # Execute tools assigned to this agent
    for tool_call in planned:
        name = tool_call.get("name")
        args = tool_call.get("args", {})

        if TOOL_TO_AGENT.get(name) != agent_name:
            continue

        if name not in tools:
            continue

        try:
            logger.info(f"Agent '{agent_name}' invoking tool '{name}' with args: {args}")
            tool_func = tools[name]

            # Resolve company_id placeholder: prefer state, then fall back to first DB company
            needs_company_id = (
                args.get("company_id") == "__resolve_from_ticker__"
                or (name == "search_knowledge" and not args.get("company_id"))
            )
            if needs_company_id:
                if company_details:
                    args["company_id"] = company_details.get("id")
                else:
                    try:
                        from app.services.company import CompanyService
                        from app.models.document_chunk import DocumentChunk
                        from sqlalchemy import select, func
                        company_svc = CompanyService(db)
                        # Pick the first company that actually has ingested document chunks
                        # (avoids defaulting to an empty company that has no knowledge base)
                        chunk_count_stmt = (
                            select(DocumentChunk.company_id, func.count(DocumentChunk.id).label("cnt"))
                            .group_by(DocumentChunk.company_id)
                            .order_by(func.count(DocumentChunk.id).desc())
                            .limit(1)
                        )
                        chunk_res = await db.execute(chunk_count_stmt)
                        top_company_id = chunk_res.scalars().first()
                        if top_company_id:
                            fallback = await company_svc.repository.get(top_company_id)
                        else:
                            all_companies = await company_svc.repository.get_multi(limit=1)
                            fallback = all_companies[0] if all_companies else None
                        if fallback:
                            company_details = {
                                "id": str(fallback.id),
                                "company_name": fallback.company_name,
                                "ticker_symbol": fallback.ticker_symbol,
                                "exchange": getattr(fallback, "exchange", None),
                                "sector": getattr(fallback, "sector", None),
                                "industry": getattr(fallback, "industry", None),
                            }
                            args["company_id"] = company_details["id"]
                            logger.info(
                                f"Agent '{agent_name}': no company in query context, "
                                f"defaulted to '{company_details['company_name']}' "
                                f"(id={company_details['id']}, has most chunks)"
                            )
                    except Exception as lookup_err:
                        logger.warning(f"Agent '{agent_name}': fallback company lookup failed: {lookup_err}")

            result = await tool_func.ainvoke(args)
            history.append(name)

            # Store result in node outputs mapping
            agent_outputs[name] = result

            # Update shared state components
            if name == "get_company_by_ticker" and result:
                company_details = result
            elif name == "search_knowledge" and result:
                retrieved_chunks.extend(result)
            elif name == "list_documents" and result:
                document_metadata.extend(result)
            elif name == "get_document_metadata" and result:
                document_metadata.append(result)
            elif name == "analyze_event_intelligence" and result:
                companies = result.get("potentially_impacted_companies", [])
                for c in companies:
                    for ev in c.get("evidence", []):
                        retrieved_chunks.append({
                            "chunk_text": ev.get("chunk_text"),
                            "document_title": ev.get("document_title"),
                            "page_number": ev.get("page_number"),
                            "section_title": ev.get("section_title"),
                            "similarity_score": ev.get("similarity_score"),
                        })
            elif name == "analyze_financial_intelligence" and result:
                for ev in result.get("financial_evidence", []):
                    if ev.get("chunk_text"):
                        retrieved_chunks.append({
                            "chunk_text": ev.get("chunk_text"),
                            "document_title": ev.get("document_title"),
                            "page_number": ev.get("page_number"),
                            "section_title": ev.get("section_title"),
                            "similarity_score": ev.get("similarity_score"),
                        })

        except Exception as e:
            logger.error(f"Agent '{agent_name}' encountered error running tool '{name}': {e}")

    # For compatibility, we can also record that the agent itself executed
    history.append(agent_name)

    return {
        "company_details": company_details,
        "retrieved_chunks": retrieved_chunks,
        "document_metadata": document_metadata,
        "execution_history": history,
        "agent_outputs": agent_outputs

    }


# ── Individual Node Implementations ───────────────────────────────────────────

async def company_analysis_node(state: ExtendedAgentState, config: RunnableConfig) -> Dict[str, Any]:
    return await execute_agent_node("company_analysis", state, config)

async def financial_statement_node(state: ExtendedAgentState, config: RunnableConfig) -> Dict[str, Any]:
    return await execute_agent_node("financial_statement", state, config)

async def news_intelligence_node(state: ExtendedAgentState, config: RunnableConfig) -> Dict[str, Any]:
    return await execute_agent_node("news_intelligence", state, config)

async def event_intelligence_node(state: ExtendedAgentState, config: RunnableConfig) -> Dict[str, Any]:
    return await execute_agent_node("event_intelligence", state, config)

async def valuation_node(state: ExtendedAgentState, config: RunnableConfig) -> Dict[str, Any]:
    return await execute_agent_node("valuation", state, config)

async def risk_analysis_node(state: ExtendedAgentState, config: RunnableConfig) -> Dict[str, Any]:
    return await execute_agent_node("risk_analysis", state, config)


# ── Report Generation (Final Assembly) Node ───────────────────────────────────

async def report_generation_node(state: ExtendedAgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Report Generation Agent: Compiles final context and synthesizes AI summaries.
    """
    logger.info("Report generation node running final execution context compilation.")
    
    agent_outputs = state.get("agent_outputs", {})
    company_details = state.get("company_details")
    document_metadata = state.get("document_metadata", [])
    retrieved_chunks = state.get("retrieved_chunks", [])
    history = list(state.get("execution_history", []))

    # Initialize final context base
    final_context = {
        "summary": f"Context assembled for query: '{state.get('user_query')}'",
        "company_info": company_details,
        "related_documents": document_metadata,
        "search_matches": retrieved_chunks,
    }

    # Overlay specialized outputs from agent logs
    if "analyze_event_intelligence" in agent_outputs:
        final_context["event_intelligence"] = agent_outputs["analyze_event_intelligence"]
    if "analyze_financial_intelligence" in agent_outputs:
        final_context["financial_intelligence"] = agent_outputs["analyze_financial_intelligence"]
    if "calculate_company_valuation" in agent_outputs:
        final_context["valuation"] = agent_outputs["calculate_company_valuation"]
    if "generate_research_report" in agent_outputs:
        final_context["research_report"] = agent_outputs["generate_research_report"]

    history.append("report_generation")

    return {
        "execution_history": history,
        "final_context": final_context
    }


# ── StateGraph Assembly ───────────────────────────────────────────────────────

workflow = StateGraph(ExtendedAgentState)

# Add Node Implementations
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("company_analysis", company_analysis_node)
workflow.add_node("financial_statement", financial_statement_node)
workflow.add_node("news_intelligence", news_intelligence_node)
workflow.add_node("event_intelligence", event_intelligence_node)
workflow.add_node("valuation", valuation_node)
workflow.add_node("risk_analysis", risk_analysis_node)
workflow.add_node("report_generation", report_generation_node)

# Set Entry Point
workflow.add_edge(START, "supervisor")

# Configure Router Edge Connections
routing_rules = {
    "company_analysis": "company_analysis",
    "financial_statement": "financial_statement",
    "news_intelligence": "news_intelligence",
    "event_intelligence": "event_intelligence",
    "valuation": "valuation",
    "risk_analysis": "risk_analysis",
    "report_generation": "report_generation"
}

# Bind Conditional Transitions from routing edges
workflow.add_conditional_edges("supervisor", route_next_agent, routing_rules)
workflow.add_conditional_edges("company_analysis", route_next_agent, routing_rules)
workflow.add_conditional_edges("financial_statement", route_next_agent, routing_rules)
workflow.add_conditional_edges("news_intelligence", route_next_agent, routing_rules)
workflow.add_conditional_edges("event_intelligence", route_next_agent, routing_rules)
workflow.add_conditional_edges("valuation", route_next_agent, routing_rules)
workflow.add_conditional_edges("risk_analysis", route_next_agent, routing_rules)

# Direct Exit from report generator
workflow.add_edge("report_generation", END)

# Compile Graph Orchestrator
orchestrator_graph = workflow.compile()


# ── Backward Compatibility Wrapper ───────────────────────────────────────────

async def tool_execution_node(state: ExtendedAgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Compatibility helper implementing sequential tool execution for legacy test expectations."""
    db: AsyncSession = config.get("configurable", {}).get("db")
    if not db:
        raise ValueError("Database session is required in config.")

    tools = create_tools(db)
    planned = state.get("planned_tools", [])
    history = list(state.get("execution_history", []))

    retrieved_chunks = list(state.get("retrieved_chunks", []))
    company_details = state.get("company_details")
    document_metadata = list(state.get("document_metadata", []))
    final_context = dict(state.get("final_context", {}))

    for tool_call in planned:
        name = tool_call.get("name")
        args = tool_call.get("args", {})

        if name not in tools:
            continue

        try:
            tool_func = tools[name]
            if args.get("company_id") == "__resolve_from_ticker__" and company_details:
                args["company_id"] = company_details.get("id")

            result = await tool_func.ainvoke(args)
            history.append(name)

            if name == "get_company_by_ticker" and result:
                company_details = result
            elif name == "search_knowledge" and result:
                retrieved_chunks.extend(result)
            elif name == "list_documents" and result:
                document_metadata.extend(result)
            elif name == "get_document_metadata" and result:
                document_metadata.append(result)
            elif name == "analyze_event_intelligence" and result:
                companies = result.get("potentially_impacted_companies", [])
                for c in companies:
                    for ev in c.get("evidence", []):
                        retrieved_chunks.append({
                            "chunk_text": ev.get("chunk_text"),
                            "document_title": ev.get("document_title"),
                            "page_number": ev.get("page_number"),
                            "section_title": ev.get("section_title"),
                            "similarity_score": ev.get("similarity_score"),
                        })
            elif name == "analyze_financial_intelligence" and result:
                for ev in result.get("financial_evidence", []):
                    if ev.get("chunk_text"):
                        retrieved_chunks.append({
                            "chunk_text": ev.get("chunk_text"),
                            "document_title": ev.get("document_title"),
                            "page_number": ev.get("page_number"),
                            "section_title": ev.get("section_title"),
                            "similarity_score": ev.get("similarity_score"),
                        })

        except Exception as e:
            logger.error(f"Error executing tool '{name}' in compatibility node: {e}")

    final_context.update({
        "summary": f"Context assembled for query: '{state.get('user_query')}'",
        "company_info": company_details,
        "related_documents": document_metadata,
        "search_matches": retrieved_chunks,
    })

    return {
        "retrieved_chunks": retrieved_chunks,
        "company_details": company_details,
        "document_metadata": document_metadata,
        "execution_history": history,
        "final_context": final_context,
    }

