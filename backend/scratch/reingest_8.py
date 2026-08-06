import sys, os
sys.path.insert(0, os.path.abspath("."))

import asyncio
from sqlalchemy import select, func, text
from app.models.document import Document, ProcessingStatus
from app.models.document_chunk import DocumentChunk
from app.models.company import Company
from app.services.tasks import process_document

async def run_repair():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.core.config import settings

    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    target_ids = [
        '057fcf33-29d6-42a2-88f3-9053339c8b42',
        '6af71db9-b200-455c-9072-57ff4d235b84',
        '36988a45-3ed7-4397-8a85-27ad562dd1a5',
        'b9886a20-2517-4d90-a034-dce6b67d3f75',
        'd2c8e980-e32e-4f20-af35-6adbdac31bc2',
        '86a3bfae-b2f5-42e2-a195-552ba13c8665',
        '208470b5-0b00-4299-847d-799bf4ab86fa',
        '18b55ab1-26dd-4e5b-b868-03bf43772d11',
    ]

    failing_docs = []
    async with async_session() as db:
        stmt = select(Document, Company.company_name).join(Company, Document.company_id == Company.id).where(Document.id.in_(target_ids))
        res = await db.execute(stmt)
        for doc, company_name in res.all():
            chunk_cnt = (await db.execute(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == doc.id))).scalar()
            failing_docs.append((doc.id, doc.file_name, company_name, doc.file_size))

    print(f"Target documents count: {len(failing_docs)}")
    for doc_id, fname, comp, fsize in failing_docs:
        print(f" - ID: {doc_id} | Company: {comp} | File: {fname} ({fsize/(1024*1024):.2f} MB)")

    # Reset processing_status to pending
    async with async_session() as db:
        for doc_id, _, _, _ in failing_docs:
            doc = (await db.execute(select(Document).where(Document.id == doc_id))).scalars().first()
            doc.processing_status = ProcessingStatus.pending
            db.add(doc)
        await db.commit()
        print("Reset status to pending for all 8 documents.")

    # Re-trigger process_document for each of the 8 documents
    results = {}
    for idx, (doc_id, fname, comp, fsize) in enumerate(failing_docs, 1):
        print(f"\n[{idx}/8] Re-ingesting document: {fname} ({comp}, {fsize/(1024*1024):.2f} MB)...")
        try:
            await process_document(doc_id)
            async with async_session() as db:
                cnt = (await db.execute(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == doc_id))).scalar()
                doc = (await db.execute(select(Document).where(Document.id == doc_id))).scalars().first()
            results[fname] = {'status': doc.processing_status.value, 'chunks_saved': cnt, 'company': comp}
            print(f"SUCCESS! {fname} ingested -> status: {doc.processing_status.value}, chunks saved: {cnt}")
        except Exception as e:
            async with async_session() as db:
                cnt = (await db.execute(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == doc_id))).scalar()
                doc = (await db.execute(select(Document).where(Document.id == doc_id))).scalars().first()
            results[fname] = {'status': doc.processing_status.value, 'chunks_saved': cnt, 'error': str(e), 'company': comp}
            print(f"FAILED: {fname} -> status: {doc.processing_status.value}, error: {e}")

    print("\n================ RE-INGESTION REPORT ================")
    for fname, r in results.items():
        print(f"{r['company']:<40} | File: {fname:<35} | Status: {r['status']:<10} | SavedChunks: {r['chunks_saved']}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_repair())
