import asyncio
from app.db.session import SessionLocal
from app.services.event_impact import EventImpactService

async def main():
    async with SessionLocal() as db:
        service = EventImpactService(db)
        
        print("=== TEST CASE 1: Event query for TVSSCS (Oil price / supply chain disruption) ===")
        res1 = await service.analyze_event_impact(
            user_query="How has the Iran-US war oil price increase affected TVSSCS?",
            ticker_symbol="TVSSCS"
        )
        print(f"Provider: {res1.provider}")
        print(f"Executive Summary: {res1.executive_summary}")
        print(f"Sources Count: {len(res1.sources)}")
        print(f"Sources: {res1.sources[:3]}")
        print(f"Detailed Citations: {res1.cited_sources_detailed[:3]}")
        print()

        print("=== TEST CASE 2: Unrelated event with NO company connection (Expect Fallback Message) ===")
        res2 = await service.analyze_event_impact(
            user_query="How has the lunar eclipse affected TVSSCS underwater mining operations?",
            ticker_symbol="TVSSCS"
        )
        print(f"Provider: {res2.provider}")
        print(f"Executive Summary: {res2.executive_summary}")
        print(f"Sources Count: {len(res2.sources)}")
        print(f"Fallback Verified: {'No disclosed risk factors' in res2.executive_summary}")

if __name__ == "__main__":
    asyncio.run(main())
