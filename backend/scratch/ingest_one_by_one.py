import sys, os, subprocess
sys.path.insert(0, os.path.abspath("."))

import asyncio
from sqlalchemy import select, text
from app.models.document import Document, ProcessingStatus
from app.models.company import Company
from app.services.tasks import process_document

target_files = [
    ("Omax Autos Limited", "Omax_AR.pdf"),
    ("HB Stockholdings Limited", "HB_AR.pdf"),
    ("Expleo Solutions Limited", "Expelo_AR.pdf"),
    ("Suven Life Sciences Limited", "Suven_AR.pdf"),
    ("Vivo Collaboration Solutions Limited", "Vivo_AR.pdf"),
    ("Steel Exchange India Limited", "Steel_Exchnge_AR.pdf"),
    ("Bondada Engineering Limited", "Bondada_AR.pdf"),
    ("VIP Industries Limited", "VIP_AR.pdf"),
]

def query_docker_db(file_name: str) -> tuple[str, str, int]:
    cmd = [
        "docker", "exec", "finiq_db", "psql", "-U", "postgres", "-d", "finiq", "-t", "-c",
        f"SELECT d.file_name, d.processing_status, count(dc.id) as chunk_count FROM documents d LEFT JOIN document_chunks dc ON dc.document_id = d.id WHERE d.file_name = '{file_name}' GROUP BY d.file_name, d.processing_status;"
    ]
    res = subprocess.check_output(cmd, text=True).strip()
    parts = [p.strip() for p in res.split("|") if p.strip()]
    if len(parts) == 3:
        fname, status, count_str = parts
        return fname, status, int(count_str)
    raise RuntimeError(f"Unexpected query output for {file_name}: '{res}'")

async def run_sequential():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.core.config import settings

    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    print("================ STEP 4: RESET ALL 8 DOCUMENTS TO PENDING ================")
    async with async_session() as db:
        for comp, fname in target_files:
            doc = (await db.execute(select(Document).where(Document.file_name == fname))).scalars().first()
            if doc:
                doc.processing_status = ProcessingStatus.pending
                db.add(doc)
        await db.commit()
    print("Reset all 8 documents to 'pending' in database.")

    summary = []
    for idx, (comp_name, fname) in enumerate(target_files, 1):
        print(f"\n------------------------------------------------------------------------")
        print(f"[{idx}/8] INGESTING DOCUMENT: '{fname}' ({comp_name})...")
        print(f"------------------------------------------------------------------------")
        
        async with async_session() as db:
            doc = (await db.execute(select(Document).where(Document.file_name == fname))).scalars().first()
            doc_id = str(doc.id)

        try:
            await process_document(doc_id)
        except Exception as err:
            print(f"ERROR processing {fname}: {err}")

        # LIVE HARD VERIFICATION via docker exec against real finiq_db container
        db_fname, db_status, db_chunk_count = query_docker_db(fname)
        print(f"LIVE DOCKER DB VERIFICATION FOR {fname}:")
        print(f"  -> File: {db_fname}")
        print(f"  -> Processing Status: {db_status}")
        print(f"  -> Chunk Count Saved in DB: {db_chunk_count}")

        if db_status == "completed" and db_chunk_count == 0:
            print(f"CRITICAL FAILURE: {fname} marked completed with 0 chunks! STOPPING IMMEDIATELY.")
            sys.exit(1)

        summary.append((comp_name, fname, db_status, db_chunk_count))

    print("\n================ FINAL SEQUENTIAL INGESTION SUMMARY ================")
    for comp, fname, st, cnt in summary:
        print(f"{comp:<40} | File: {fname:<30} | Status: {st:<10} | Saved Chunks: {cnt}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_sequential())
