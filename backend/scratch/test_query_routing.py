import asyncio
from app.ai.orchestrator.graph import supervisor_node

async def run():
    state = {
        "user_query": "what does tvs do?",
        "planned_tools": [],
        "planned_agents": [],
        "execution_history": [],
    }
    res = await supervisor_node(state, {})
    print("ROUTED PLANNED TOOLS:", res.get("planned_tools"))
    print("ROUTED PLANNED AGENTS:", res.get("planned_agents"))

if __name__ == "__main__":
    asyncio.run(run())
