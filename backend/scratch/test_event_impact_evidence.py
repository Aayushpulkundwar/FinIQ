import os
os.environ['OLLAMA_BASE_URL'] = 'http://localhost:11434'
import asyncio
import json
from app.db.session import SessionLocal
from app.services.event_impact import EventImpactService

async def run_evidence_tests():
    from app.core.config import settings
    settings.ALLOW_MOCK_LLM = True
    async with SessionLocal() as db:
        svc = EventImpactService(db)

        print("==================================================")
        print("TEST 1: Real Event Query ('How does oil price increase affect TVSSCS?')")
        print("==================================================")
        res1 = await svc.analyze_event_impact("How does oil price increase affect TVSSCS?", ticker_symbol="TVSSCS")
        print("Provider:", res1.provider)
        print("Generation Mode:", res1.generation_mode)
        print("\n[LITERAL EXECUTIVE SUMMARY]:")
        print(res1.executive_summary)
        print("\n[LITERAL KEY INSIGHTS]:")
        print(json.dumps(res1.key_insights, indent=2))
        print("\n[LITERAL SUPPORTING EVIDENCE]:")
        print(json.dumps(res1.supporting_evidence, indent=2))
        print("\n[LITERAL CITED_SOURCES_DETAILED ARRAY]:")
        print(json.dumps(res1.cited_sources_detailed, indent=2))
        print()

        print("==================================================")
        print("TEST 2: Nonsense Query ('How does lunar eclipse affect TVSSCS underwater mining?')")
        print("==================================================")
        res2 = await svc.analyze_event_impact("How does lunar eclipse affect TVSSCS underwater mining?", ticker_symbol="TVSSCS")
        print("Provider:", res2.provider)
        print("Generation Mode:", res2.generation_mode)
        print("\n[LITERAL EXECUTIVE SUMMARY]:")
        print(res2.executive_summary)
        print("\n[LITERAL CITED_SOURCES_DETAILED ARRAY]:")
        print(json.dumps(res2.cited_sources_detailed, indent=2))
        print("Fallback string matches expected exactly:", "No disclosed risk factors or recent news related to this event were found for TVS Supply Chain Solutions Limited." in res2.executive_summary)
        print()

        print("==================================================")
        print("TEST 3: Single-Source Coverage (Annual Report Risk Factors match, 0 news)")
        print("==================================================")
        res3 = await svc.analyze_event_impact("How do foreign exchange rate volatility and interest rate fluctuations impact TVSSCS?", ticker_symbol="TVSSCS")
        print("Provider:", res3.provider)
        print("Generation Mode:", res3.generation_mode)
        print("\n[LITERAL EXECUTIVE SUMMARY]:")
        print(res3.executive_summary)
        print("\n[LITERAL CITED_SOURCES_DETAILED ARRAY]:")
        print(json.dumps(res3.cited_sources_detailed, indent=2))

if __name__ == "__main__":
    asyncio.run(run_evidence_tests())
