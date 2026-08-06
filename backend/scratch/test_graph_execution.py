import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import SessionLocal
from app.ai.orchestrator.graph import orchestrator_graph
from app.services.company import CompanyService

async def run():
    async with SessionLocal() as db:
        company_svc = CompanyService(db)
        companies = await company_svc.repository.get_multi(limit=5)
        print("COMPANIES IN DB:", [(c.company_name, c.ticker_symbol, c.id) for c in companies])

        tvs_comp = None
        for c in companies:
            if "tvs" in c.company_name.lower() or "tvs" in c.ticker_symbol.lower():
                tvs_comp = c
                break

        state_input = {
            "user_query": "what does tvs do?",
            "retrieved_chunks": [],
            "company_details": {
                "id": str(tvs_comp.id),
                "company_name": tvs_comp.company_name,
                "ticker_symbol": tvs_comp.ticker_symbol,
            } if tvs_comp else None,
            "company_id": str(tvs_comp.id) if tvs_comp else None,
            "document_metadata": [],
            "execution_history": [],
            "final_context": {},
        }

        print("INVOKING GRAPH WITH STATE:", state_input)
        final_state = await orchestrator_graph.ainvoke(
            state_input,
            config={"configurable": {"db": db}}
        )

        print("\n=== FINAL STATE KEYS ===")
        print("Planned tools:", final_state.get("planned_tools"))
        print("Execution history:", final_state.get("execution_history"))
        print("Company details:", final_state.get("company_details"))
        print("Retrieved chunks count:", len(final_state.get("retrieved_chunks", [])))
        for idx, chunk in enumerate(final_state.get("retrieved_chunks", [])[:3]):
            print(f"Chunk #{idx+1}:", chunk.get("document_title"), "Page", chunk.get("page_number"), chunk.get("chunk_text")[:100])

if __name__ == "__main__":
    asyncio.run(run())
