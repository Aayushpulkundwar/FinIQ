import asyncio
from app.db.session import SessionLocal
from app.services.company import CompanyService
from app.services.response_generation import ResponseGenerationService

async def main():
    async with SessionLocal() as db:
        service = CompanyService(db)
        resp_service = ResponseGenerationService()
        companies = await service.list_companies()
        
        for c in companies:
            print(f"=== Testing 5x News Summarization for {c.ticker_symbol} ===")
            for i in range(5):
                cdict = {
                    "id": str(c.id),
                    "company_name": c.company_name,
                    "ticker_symbol": c.ticker_symbol,
                    "exchange": c.exchange
                }
                chunks = [
                    {
                        "document_title": f"{c.ticker_symbol} News Article {j}",
                        "chunk_text": f"Recent headline {j} regarding {c.company_name} financial growth, earnings expansion, and market position.",
                        "url": "https://example.com"
                    } for j in range(5)
                ]
                res = await resp_service.generate_response(
                    user_query=f"Summarize latest news and market updates for {c.company_name}",
                    retrieved_chunks=chunks,
                    company_details=cdict,
                    document_metadata=[]
                )
                summary_preview = res.executive_summary[:65].replace("\n", " ")
                print(f"  Run {i+1}: mode={res.generation_mode}, degraded={res.is_degraded}, exec_summary_prefix='{summary_preview}...'")

if __name__ == "__main__":
    asyncio.run(main())
