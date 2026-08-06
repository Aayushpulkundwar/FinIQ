"""
Phase 2 Hard-Test — Single-file ingestion helper.
Usage: python phase2_ingest.py <pdf_path> <company_name> <title> <fiscal_year>

Steps:
1. Creates company if it doesn't exist
2. Uploads the PDF via multipart POST /api/v1/documents
3. Polls processing_status every 15s, printing heartbeat_at each poll
4. On completion, prints psql verification (chunk count, null embeddings)
5. Exits with code 0 on success, 1 on failure/stall
"""
import sys
import time
import requests
from datetime import datetime

API = "http://localhost:8000/api/v1"
STALL_TIMEOUT_S = 3600   # 1 hour max per file
POLL_INTERVAL_S = 15


def get_or_create_company(name: str) -> str:
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from app.core.config import settings
    from app.services.company import CompanyService
    from app.schemas.company import CompanyCreate

    async def _do():
        engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, echo=False, future=True)
        SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        async with SessionLocal() as db:
            service = CompanyService(db)
            companies = await service.repository.get_multi(limit=100)
            for c in companies:
                if c.company_name.lower() == name.lower():
                    await engine.dispose()
                    return str(c.id)
            ticker = name.split()[0].upper()[:8]
            payload = CompanyCreate(
                company_name=name,
                ticker_symbol=ticker,
                exchange="NSE",
                isin=f"INE{ticker[:3]}00001",
                sector="Unknown",
                industry="Unknown",
                country="India",
            )
            c = await service.create_company(payload)
            await db.commit()
            cid = str(c.id)
        await engine.dispose()
        return cid

    return asyncio.run(_do())


def upload_document(pdf_path: str, company_id: str, title: str, fiscal_year: int) -> dict:
    import asyncio
    import io
    import os
    import uuid
    from fastapi import UploadFile
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from app.core.config import settings
    from app.services.document import DocumentService
    from app.models.document import DocumentType

    async def _do_upload():
        engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, echo=False, future=True)
        SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        file_name = os.path.basename(pdf_path)
        with open(pdf_path, "rb") as f:
            content = f.read()
        file_obj = UploadFile(filename=file_name, file=io.BytesIO(content))
        async with SessionLocal() as db:
            service = DocumentService(db)
            doc = await service.upload_document(
                company_id=uuid.UUID(company_id),
                title=title,
                document_type=DocumentType.annual_report,
                fiscal_year=fiscal_year,
                quarter=None,
                file=file_obj,
                allow_supersede=True,
            )
            res = {"id": str(doc.id), "title": doc.title, "processing_status": str(doc.processing_status.value)}
        await engine.dispose()
        return res

    return asyncio.run(_do_upload())


def poll_until_done(doc_id: str, title: str) -> dict:
    start = time.time()
    last_heartbeat = None
    last_heartbeat_seen = None
    last_heartbeat_change_time = time.time()
    heartbeat_changes = 0
    poll_count = 0

    print(f"\n  Polling every {POLL_INTERVAL_S}s (max {STALL_TIMEOUT_S//60}min)...")
    print(f"  {'Time':>6}  {'Status':20}  {'heartbeat_at'}")
    print(f"  {'-'*6}  {'-'*20}  {'-'*30}")

    while True:
        elapsed = int(time.time() - start)
        import asyncio
        import uuid
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
        from app.core.config import settings
        from app.repositories.document import DocumentRepository

        async def _get_doc():
            engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, echo=False, future=True)
            SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
            async with SessionLocal() as db:
                repo = DocumentRepository(db)
                d = await repo.get(id=uuid.UUID(doc_id))
                res = {
                    "processing_status": str(d.processing_status.value) if d and d.processing_status else "unknown",
                    "heartbeat_at": d.heartbeat_at.isoformat() if d and d.heartbeat_at else None,
                }
            await engine.dispose()
            return res

        doc = asyncio.run(_get_doc())
        status = doc.get("processing_status", "?")
        hb = doc.get("heartbeat_at", None)
        poll_count += 1

        hb_str = hb[:23] if hb else "NULL"
        if hb and hb != last_heartbeat:
            heartbeat_changes += 1
            last_heartbeat = hb
            hb_marker = " ← updated"
        else:
            hb_marker = ""

        print(f"  {elapsed:>5}s  {status:20}  {hb_str}{hb_marker}")

        if status == "completed":
            elapsed_total = time.time() - start
            print(f"\n  ✓ COMPLETED in {elapsed_total:.0f}s ({elapsed_total/60:.1f}min)")
            print(f"  heartbeat_at updated {heartbeat_changes} times during run")
            return doc

        if status == "failed":
            print(f"\n  ✗ FAILED after {elapsed:.0f}s")
            return doc

        if elapsed > STALL_TIMEOUT_S:
            print(f"\n  ✗ STALL: still '{status}' after {STALL_TIMEOUT_S//60}min — stopping")
            return {"processing_status": "stalled"}

        # Check for stall: heartbeat not updated in 15 min while processing
        if status == "processing":
            if hb and hb != last_heartbeat_seen:
                last_heartbeat_seen = hb
                last_heartbeat_change_time = time.time()
            elif (time.time() - last_heartbeat_change_time) > 900:
                print(f"\n  ✗ STALL: processing with no heartbeat updates for >15min")
                return {"processing_status": "stalled"}

        time.sleep(POLL_INTERVAL_S)


def main():
    if len(sys.argv) < 5:
        print("Usage: phase2_ingest.py <pdf_path> <company_name> <title> <fiscal_year>")
        sys.exit(1)

    pdf_path, company_name, title, fiscal_year = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])

    import os
    file_size_mb = round(os.path.getsize(pdf_path) / 1024 / 1024, 1)

    print(f"\n{'='*70}")
    print(f"Phase 2 Hard-Test — {title}")
    print(f"File: {pdf_path} ({file_size_mb} MB)")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"{'='*70}")

    # Step 1: Company
    print("\n[1] Company setup...")
    company_id = get_or_create_company(company_name)

    # Step 2: Upload
    print(f"\n[2] Uploading {file_size_mb} MB PDF...")
    t0 = time.time()
    doc = upload_document(pdf_path, company_id, title, fiscal_year)
    upload_s = time.time() - t0
    doc_id = doc["id"]
    print(f"  ✓ Uploaded in {upload_s:.1f}s — doc_id={doc_id}")
    print(f"  upload_status={doc.get('upload_status')}, processing_status={doc.get('processing_status')}")

    # Step 3: Poll
    print(f"\n[3] Monitoring ingestion pipeline...")
    final = poll_until_done(doc_id, title)

    # Step 4: psql verification via direct DB query
    print(f"\n[4] DB verification for doc_id={doc_id}...")
    import asyncio as _aio
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy import text
    from app.core.config import settings

    async def _verify():
        engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, echo=False, future=True)
        SM = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        async with SM() as db:
            q = text("""
                SELECT
                    d.processing_status,
                    d.heartbeat_at IS NOT NULL AS heartbeat_set,
                    COUNT(dc.id) AS chunk_count,
                    SUM(CASE WHEN dc.embedding IS NULL THEN 1 ELSE 0 END) AS null_embeddings
                FROM documents d
                LEFT JOIN document_chunks dc ON dc.document_id = d.id
                WHERE d.id = :doc_id
                GROUP BY d.processing_status, d.heartbeat_at
            """)
            res = await db.execute(q, {"doc_id": doc_id})
            row = res.fetchone()
            return row
        await engine.dispose()

    row = _aio.run(_verify())
    if row:
        print(f"  processing_status : {row[0]}")
        print(f"  heartbeat_set     : {row[1]}")
        print(f"  chunk_count       : {row[2]}")
        print(f"  null_embeddings   : {row[3]}")
        if row[3] and int(row[3]) > 0:
            print(f"  ✗ WARNING: {row[3]} chunks have NULL embeddings!")
        else:
            print(f"  ✓ Zero NULL embeddings")
    else:
        print("  ✗ No rows returned — document or chunks not found")

    status = final.get("processing_status")
    print(f"\n{'='*70}")
    if status == "completed":
        print(f"RESULT: ✓ PASS — {title} ingested successfully")
    else:
        print(f"RESULT: ✗ FAIL — {title} ended with status={status}")
    print(f"{'='*70}\n")

    sys.exit(0 if status == "completed" else 1)


if __name__ == "__main__":
    main()
