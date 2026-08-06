import asyncio
from app.db.session import SessionLocal
from app.ai.orchestrator.graph import orchestrator_graph
from app.services.response_generation import ResponseGenerationService
from app.services.company import CompanyService

async def main():
    async with SessionLocal() as db:
        query = "What's the latest news on TVS Supply Chain?"
        company_svc = CompanyService(db)
        companies = await company_svc.repository.get_multi()
        tvs_company = next((c for c in companies if "tvs" in c.company_name.lower()), None)
        
        state_input = {
            "user_query": query,
            "retrieved_chunks": [],
            "company_details": {
                "id": str(tvs_company.id),
                "company_name": tvs_company.company_name,
                "ticker_symbol": tvs_company.ticker_symbol,
            } if tvs_company else None,
            "company_id": str(tvs_company.id) if tvs_company else None,
            "document_metadata": [],
            "execution_history": [],
            "final_context": {},
        }
        
        print(f"Executing graph for query: '{query}'...")
        final_state = await orchestrator_graph.ainvoke(
            state_input,
            config={"configurable": {"db": db}}
        )
        
        chunks = final_state.get("retrieved_chunks", [])
        print(f"Graph execution complete! Retrieved chunks count: {len(chunks)}")
        for idx, c in enumerate(chunks, 1):
            print(f" Chunk #{idx}: {c.get('document_title')} | Page: {c.get('page_number')} | URL: {c.get('url')}")
            
        gen_svc = ResponseGenerationService()
        ai_resp = await gen_svc.generate_response(
            user_query=query,
            company_details=final_state.get("company_details"),
            document_metadata=final_state.get("document_metadata"),
            retrieved_chunks=chunks,
            db=db,
        )
        
        print(f"\n=======================================================")
        print(f"EXECUTIVE SUMMARY:\n{ai_resp.executive_summary}")
        print(f"SOURCES: {ai_resp.sources}")
        print(f"CITED SOURCES DETAILED: {ai_resp.cited_sources_detailed}")
        print(f"SUPPORTING EVIDENCE: {ai_resp.supporting_evidence}")
        print(f"GENERATION MODE: {ai_resp.generation_mode}")

if __name__ == "__main__":
    asyncio.run(main())
