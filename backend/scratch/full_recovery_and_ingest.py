import sys, os, subprocess, uuid, datetime
sys.path.insert(0, os.path.abspath("."))

import asyncio
from sqlalchemy import select, text
from app.models.document import Document, ProcessingStatus, UploadStatus, DocumentType
from app.models.company import Company
from app.services.tasks import process_document

docs_to_restore = [
    {
        "company_name": "Omax Autos Limited",
        "file_name": "Omax_AR.pdf",
        "file_size": 43049339,
        "object_path": "documents/9e0eba7e-38e6-44fa-8e11-5a34d8da4a28/d2c8e980-e32e-4f20-af35-6adbdac31bc2.pdf",
        "company_id": "9e0eba7e-38e6-44fa-8e11-5a34d8da4a28",
        "fiscal_year": 2024,
    },
    {
        "company_name": "HB Stockholdings Limited",
        "file_name": "HB_AR.pdf",
        "file_size": 44795534,
        "object_path": "documents/7555f1f2-11dc-45cd-bb59-273b551fa99e/36988a45-3ed7-4397-8a85-27ad562dd1a5.pdf",
        "company_id": "7555f1f2-11dc-45cd-bb59-273b551fa99e",
        "fiscal_year": 2024,
    },
    {
        "company_name": "Expleo Solutions Limited",
        "file_name": "Expelo_AR.pdf",
        "file_size": 45977450,
        "object_path": "documents/8a387540-3c2c-4e09-a6d5-ae9f394c4f2f/208470b5-0b00-4299-847d-799bf4ab86fa.pdf",
        "company_id": "8a387540-3c2c-4e09-a6d5-ae9f394c4f2f",
        "fiscal_year": 2024,
    },
    {
        "company_name": "Suven Life Sciences Limited",
        "file_name": "Suven_AR.pdf",
        "file_size": 58651905,
        "object_path": "documents/bf412105-fe72-4104-91dd-6fe41c0e3bf4/86a3bfae-b2f5-42e2-a195-552ba13c8665.pdf",
        "company_id": "bf412105-fe72-4104-91dd-6fe41c0e3bf4",
        "fiscal_year": 2024,
    },
    {
        "company_name": "Vivo Collaboration Solutions Limited",
        "file_name": "Vivo_AR.pdf",
        "file_size": 54721932,
        "object_path": "documents/c57d2e33-2e60-4a3b-ba18-3989447808d6/b9886a20-2517-4d90-a034-dce6b67d3f75.pdf",
        "company_id": "c57d2e33-2e60-4a3b-ba18-3989447808d6",
        "fiscal_year": 2024,
    },
    {
        "company_name": "Steel Exchange India Limited",
        "file_name": "Steel_Exchnge_AR.pdf",
        "file_size": 79093139,
        "object_path": "documents/7d115005-d0bb-465f-86ec-74bec5ba7d4c/6af71db9-b200-455c-9072-57ff4d235b84.pdf",
        "company_id": "7d115005-d0bb-465f-86ec-74bec5ba7d4c",
        "fiscal_year": 2024,
    },
    {
        "company_name": "Bondada Engineering Limited",
        "file_name": "Bondada_AR.pdf",
        "file_size": 94528868,
        "object_path": "documents/07be9808-7883-4904-9730-df40929dbdeb/057fcf33-29d6-42a2-88f3-9053339c8b42.pdf",
        "company_id": "07be9808-7883-4904-9730-df40929dbdeb",
        "fiscal_year": 2024,
    },
    {
        "company_name": "VIP Industries Limited",
        "file_name": "VIP_AR.pdf",
        "file_size": 112711390,
        "object_path": "documents/5194183d-b708-4515-b28b-067c29d3edbc/18b55ab1-26dd-4e5b-b868-03bf43772d11.pdf",
        "company_id": "5194183d-b708-4515-b28b-067c29d3edbc",
        "fiscal_year": 2024,
    },
]

def query_docker_db(file_name: str) -> tuple[str, str, int]:
    cmd = [
        "docker", "exec", "-i", "finiq_db", "psql", "-U", "postgres", "-d", "finiq", "-t", "-c",
        f"SELECT d.file_name, d.processing_status, count(dc.id) as chunk_count FROM documents d LEFT JOIN document_chunks dc ON dc.document_id = d.id WHERE d.file_name = '{file_name}' GROUP BY d.file_name, d.processing_status;"
    ]
    res = subprocess.check_output(cmd, text=True).strip()
    parts = [p.strip() for p in res.split("|") if p.strip()]
    if len(parts) == 3:
        fname, status, count_str = parts
        return fname, status, int(count_str)
    raise RuntimeError(f"Unexpected query output for {file_name}: '{res}'")

async def run_full_recovery():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.core.config import settings

    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    print("================ STEP 4A: RESTORE DOCUMENT METADATA IN DB ================")
    doc_ids = []
    async with async_session() as db:
        for item in docs_to_restore:
            existing = (await db.execute(select(Document).where(Document.file_name == item["file_name"]))).scalars().first()
            if existing:
                existing.processing_status = ProcessingStatus.pending
                db.add(existing)
                doc_ids.append((str(existing.id), item["file_name"], item["company_name"]))
            else:
                doc_id = item["object_path"].split("/")[-1].replace(".pdf", "")
                new_doc = Document(
                    id=uuid.UUID(doc_id),
                    company_id=uuid.UUID(item["company_id"]),
                    file_name=item["file_name"],
                    file_path=item["object_path"],
                    file_size=item["file_size"],
                    mime_type="application/pdf",
                    document_type=DocumentType.annual_report,
                    title=f"{item['company_name']} Annual Report FY{item['fiscal_year']}",
                    fiscal_year=item["fiscal_year"],
                    upload_status=UploadStatus.completed,
                    processing_status=ProcessingStatus.pending,
                )
                db.add(new_doc)
                doc_ids.append((doc_id, item["file_name"], item["company_name"]))
        await db.commit()

    print(f"Restored metadata for {len(doc_ids)} documents in database.")

    summary = []
    for idx, (doc_id, fname, comp_name) in enumerate(doc_ids, 1):
        print(f"\n------------------------------------------------------------------------")
        print(f"[{idx}/{len(doc_ids)}] INGESTING DOCUMENT: '{fname}' ({comp_name})...")
        print(f"------------------------------------------------------------------------")

        try:
            await process_document(doc_id)
        except Exception as err:
            print(f"ERROR during process_document for {fname}: {err}")

        # LIVE HARD VERIFICATION via docker exec against real finiq_db container
        db_fname, db_status, db_chunk_count = query_docker_db(fname)
        print(f"\nLIVE DOCKER DB VERIFICATION RESULT FOR {fname}:")
        print(f"  -> File: {db_fname}")
        print(f"  -> Processing Status: {db_status}")
        print(f"  -> Chunk Count Saved in DB: {db_chunk_count}")

        if db_status == "completed" and db_chunk_count == 0:
            print(f"CRITICAL FAILURE: {fname} marked completed with 0 chunks! STOPPING IMMEDIATELY.")
            sys.exit(1)

        summary.append((comp_name, fname, db_status, db_chunk_count))

    print("\n================ STEP 4B: FINAL SEQUENTIAL INGESTION SUMMARY ================")
    for comp, fname, st, cnt in summary:
        print(f"{comp:<40} | File: {fname:<30} | Status: {st:<10} | Saved Chunks: {cnt}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_full_recovery())
