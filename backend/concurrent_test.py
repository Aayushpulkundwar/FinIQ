"""
Concurrent ingestion + retrieval stress test (corrected task name).
Resets Arvind doc to pending, dispatches Celery ingestion,
then fires retrieval queries every 2s to test lock contention and latency.
Run INSIDE the finiq_web container: python /app/concurrent_test.py
"""
import time
import asyncio
import httpx
import sys
from datetime import datetime

sys.path.insert(0, "/app")

API_BASE = "http://localhost:8000/api/v1"
DOC_ID = "96782ade-967e-4c07-8cfd-31f5db914667"  # Arvind Limited

SEARCH_PAYLOAD = {
    "query": "What are Arvind Limited key business segments and revenue?",
    "top_k": 5,
}


async def fire_query(client: httpx.AsyncClient, label: str) -> dict:
    start = time.perf_counter()
    try:
        r = await client.post(f"{API_BASE}/retrieval/search", json=SEARCH_PAYLOAD, timeout=35.0)
        elapsed = time.perf_counter() - start
        body = r.json()
        return {
            "label": label,
            "status": r.status_code,
            "elapsed_s": round(elapsed, 3),
            "chunks": len(body) if r.status_code == 200 else 0,
            "detail": body.get("detail") if r.status_code != 200 else None,
        }
    except Exception as e:
        elapsed = time.perf_counter() - start
        return {"label": label, "status": "ERR", "elapsed_s": round(elapsed, 3), "error": str(e)}


def trigger_ingestion():
    """Reset doc to pending in DB, then dispatch Celery process_document_task."""
    import asyncio as _aio
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.core.config import settings
    from app.repositories.document import DocumentRepository
    from app.models.document import ProcessingStatus

    async def _reset():
        engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, echo=False, future=True)
        SM = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        async with SM() as db:
            repo = DocumentRepository(db)
            doc = await repo.get(id=DOC_ID)
            if doc:
                doc.processing_status = ProcessingStatus.pending
                doc.heartbeat_at = None
                await db.commit()
                print(f"  DB reset: {doc.title} → status=pending")
            else:
                print("  ERROR: Document not found in DB")
        await engine.dispose()

    _aio.run(_reset())

    from app.services.tasks import process_document_task
    result = process_document_task.delay(DOC_ID)
    return f"Dispatched process_document_task — task_id={result.id}"


async def main():
    print(f"[{datetime.now().isoformat()}] Concurrent ingestion + retrieval stress test")
    print("=" * 70)

    # 1. Trigger ingestion
    print(f"\n[STEP 1] Resetting doc and dispatching ingestion for doc {DOC_ID}...")
    try:
        msg = trigger_ingestion()
        print(f"  {msg}")
    except Exception as e:
        print(f"  FAILED: {e}")
        print("  Continuing with retrieval-only test (no ingestion competition).")

    # Give Celery 2s to pick it up before we start querying
    await asyncio.sleep(2.0)

    async with httpx.AsyncClient() as client:
        print(f"\n[STEP 2] Firing 3 waves × 3 queries (3s apart) while ingestion runs...")
        all_results = []

        for wave in range(1, 4):
            t_offset = (wave - 1) * 3
            print(f"\n  -- Wave {wave} at T+{t_offset}s --")
            tasks = [fire_query(client, f"w{wave}q{i}") for i in range(1, 4)]
            results = await asyncio.gather(*tasks)
            for r in results:
                if r["status"] == 200:
                    print(f"    [{r['label']}] 200 OK  | {r['elapsed_s']:.3f}s | chunks={r['chunks']}")
                elif r["status"] == 503:
                    print(f"    [{r['label']}] 503 BUSY (clean 503) | {r['elapsed_s']:.3f}s | {r.get('detail')}")
                else:
                    print(f"    [{r['label']}] {r['status']} | {r['elapsed_s']:.3f}s | {r.get('detail', r.get('error'))}")
                all_results.append(r)

            if wave < 3:
                await asyncio.sleep(3.0)

    print("\n" + "=" * 70)
    total = len(all_results)
    ok = sum(1 for r in all_results if r["status"] == 200)
    busy = sum(1 for r in all_results if r["status"] == 503)
    errs = sum(1 for r in all_results if r["status"] not in (200, 503))
    lats = [r["elapsed_s"] for r in all_results]
    avg_lat = sum(lats) / total
    max_lat = max(lats)

    print(f"Total queries : {total}")
    print(f"  HTTP 200    : {ok}")
    print(f"  HTTP 503    : {busy}  (lock busy — clean)")
    print(f"  Other errs  : {errs}")
    print(f"Avg latency   : {avg_lat:.3f}s")
    print(f"Max latency   : {max_lat:.3f}s")

    if max_lat > 15.0:
        print("⚠  Max >15s — lock queue buildup or slow Ollama")
    elif max_lat > 4.5:
        print("⚠  Max >4.5s — under load during some queries")
    else:
        print("✓  All queries within expected latency range.")

    if errs:
        print(f"✗  {errs} unexpected error(s) — investigate!")
    else:
        print("✓  No unhandled errors surfaced.")


if __name__ == "__main__":
    asyncio.run(main())
