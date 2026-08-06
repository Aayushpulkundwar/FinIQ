"""
End-to-End Test for RAG Retrieval Supersede Semantics.

Test Steps:
1. Creates a test company.
2. Creates Document A (is_active=True, completed) with chunk text 'ALPHA_REVENUE_METRIC_2026'.
3. Creates Document B for same company/FY/type with allow_supersede=True.
4. Verifies Document A gets updated to is_active=False atomically.
5. Adds chunk text 'BETA_REVENUE_METRIC_2026' for Document B.
6. Executes RetrievalService.search().
7. Verifies:
   - Search returns ONLY Document B's chunk ('BETA_REVENUE_METRIC_2026').
   - Document A's chunk ('ALPHA_REVENUE_METRIC_2026') is EXCLUDED.
   - Document A remains in DB with is_active=False and its chunks intact.
"""
import asyncio
import sys
import uuid
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, text

sys.path.insert(0, "/app") if os.path.exists("/app") else sys.path.insert(0, ".")

from app.core.config import settings
from app.models.company import Company
from app.models.document import Document, DocumentType, UploadStatus, ProcessingStatus
from app.models.document_chunk import DocumentChunk
from app.services.retrieval import RetrievalService
from app.services.document import DocumentService


import io

class MockFile:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.file = io.BytesIO(content)
        self.size = len(content)
        self.content_type = "application/pdf"

    def read(self, n=-1):
        return self.file.read(n)

    def seek(self, pos, whence=0):
        return self.file.seek(pos, whence)


async def run_test():
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, echo=False, future=True)
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    print("=" * 70)
    print("STARTING E2E SUPERSEDE RETRIEVAL TEST")
    print("=" * 70)

    async with Session() as db:
        # 1. Setup Test Company
        rnd = uuid.uuid4().hex[:6].upper()
        test_company = Company(
            id=uuid.uuid4(),
            company_name=f"Supersede Test Corp {rnd}",
            ticker_symbol=f"SUP{rnd}",
            exchange="NSE",
            isin=f"INESUPER{rnd}",
            sector="Tech",
            industry="Software",
        )
        db.add(test_company)
        await db.commit()
        print(f"\n[1] Created Test Company: {test_company.company_name} (ID: {test_company.id})")

        doc_svc = DocumentService(db)

        # 2. Upload Document A (Original)
        file_a = MockFile("DocA.pdf", b"Dummy PDF bytes for Document A")
        doc_a = await doc_svc.upload_document(
            company_id=test_company.id,
            title="Annual Report FY2026 - Version 1 (Doc A)",
            document_type=DocumentType.annual_report,
            fiscal_year=2026,
            quarter=None,
            file=file_a,
            allow_supersede=False,
        )
        doc_a.processing_status = ProcessingStatus.completed
        await db.commit()
        print(f"[2] Uploaded Doc A: {doc_a.id} | is_active={doc_a.is_active} | status={doc_a.processing_status}")

        from app.rag.embeddings import EmbeddingService
        embedder = EmbeddingService()
        emb_a = embedder.get_embedding("ALPHA_REVENUE_METRIC_2026: Total revenue was 100 Crore in FY2026.")

        # Add chunk for Doc A
        chunk_a = DocumentChunk(
            id=uuid.uuid4(),
            document_id=doc_a.id,
            company_id=test_company.id,
            chunk_text="ALPHA_REVENUE_METRIC_2026: Total revenue was 100 Crore in FY2026.",
            embedding=emb_a,
            is_mock_embedding=False,
            page_number=1,
            chunk_index=0,
            document_type=DocumentType.annual_report,
            fiscal_year=2026,
            section_title="Financial Performance",
        )
        db.add(chunk_a)
        await db.commit()
        print(f"    Added Chunk A to Doc A: '{chunk_a.chunk_text[:40]}...'")

        # 3. Test Manual Upload Guard (allow_supersede=False should raise ValueError)
        print("\n[3] Testing Manual Re-upload Guard (allow_supersede=False)...")
        file_b_dup = MockFile("DocB_dup.pdf", b"Different bytes to avoid SHA256 collision - Version B Dup")
        try:
            await doc_svc.upload_document(
                company_id=test_company.id,
                title="Annual Report FY2026 - Version 2 (Attempt 1)",
                document_type=DocumentType.annual_report,
                fiscal_year=2026,
                quarter=None,
                file=file_b_dup,
                allow_supersede=False,
            )
            print("  ✗ ERROR: Manual upload guard failed to raise ValueError!")
        except ValueError as val_err:
            print(f"  ✓ SUCCESS: Manual upload guard correctly blocked duplicate: '{val_err}'")

        # 4. Upload Document B with allow_supersede=True (Replacement)
        print("\n[4] Uploading Replacement Doc B (allow_supersede=True)...")
        file_b = MockFile("DocB.pdf", b"Different bytes for Document B replacement version")
        doc_b = await doc_svc.upload_document(
            company_id=test_company.id,
            title="Annual Report FY2026 - Version 2 (Doc B Replacement)",
            document_type=DocumentType.annual_report,
            fiscal_year=2026,
            quarter=None,
            file=file_b,
            allow_supersede=True,
        )
        doc_b.processing_status = ProcessingStatus.completed
        await db.commit()

        # Re-query Doc A to check updated status
        doc_a_updated = await db.get(Document, doc_a.id)
        print(f"  ✓ Uploaded Doc B: {doc_b.id} | is_active={doc_b.is_active}")
        print(f"  ✓ Doc A Status After Supersede: is_active={doc_a_updated.is_active} | processing_status={doc_a_updated.processing_status}")

        emb_b = embedder.get_embedding("BETA_REVENUE_METRIC_2026: Restated total revenue was 120 Crore in FY2026.")

        # Add chunk for Doc B
        chunk_b = DocumentChunk(
            id=uuid.uuid4(),
            document_id=doc_b.id,
            company_id=test_company.id,
            chunk_text="BETA_REVENUE_METRIC_2026: Restated total revenue was 120 Crore in FY2026.",
            embedding=emb_b,
            is_mock_embedding=False,
            page_number=1,
            chunk_index=0,
            document_type=DocumentType.annual_report,
            fiscal_year=2026,
            section_title="Financial Performance",
        )
        db.add(chunk_b)
        await db.commit()
        print(f"    Added Chunk B to Doc B: '{chunk_b.chunk_text[:40]}...'")

        # 5. Execute Retrieval Search
        print("\n[5] Executing RetrievalService.search() across FY2026 chunks...")
        retrieval_svc = RetrievalService(db)
        results = await retrieval_svc.search(
            query="REVENUE_METRIC_2026",
            company_id=test_company.id,
            top_k=10,
            include_mock=True,
        )

        print(f"\n[6] RETRIEVAL RESULTS ({len(results)} chunks returned):")
        for idx, res in enumerate(results, 1):
            print(f"    Result #{idx}: doc_id={res.document_id} | title='{res.document_title}' | text='{res.chunk_text}'")

        # 6. Assertions
        returned_doc_ids = [r.document_id for r in results]
        returned_texts = [r.chunk_text for r in results]

        print("\n" + "=" * 70)
        print("VERIFICATION CHECKS:")
        print("=" * 70)

        # Check A: Doc B chunk returned
        b_included = any("BETA_REVENUE_METRIC_2026" in t for t in returned_texts)
        print(f"  Check 1: Doc B active chunk returned         : {'✓ PASS' if b_included else '✗ FAIL'}")

        # Check B: Doc A chunk excluded
        a_excluded = not any("ALPHA_REVENUE_METRIC_2026" in t for t in returned_texts)
        print(f"  Check 2: Doc A superseded chunk excluded     : {'✓ PASS' if a_excluded else '✗ FAIL'}")

        # Check C: Doc A remains in DB with is_active=False
        doc_a_db = await db.get(Document, doc_a.id)
        is_inactive_in_db = doc_a_db is not None and doc_a_db.is_active is False
        print(f"  Check 3: Doc A in DB with is_active=False    : {'✓ PASS' if is_inactive_in_db else '✗ FAIL'}")

        # Check D: Doc A chunks preserved in DB (not deleted)
        chunk_a_stmt = select(DocumentChunk).where(DocumentChunk.document_id == doc_a.id)
        chunk_a_res = await db.execute(chunk_a_stmt)
        chunk_a_count = len(chunk_a_res.scalars().all())
        chunks_preserved = chunk_a_count > 0
        print(f"  Check 4: Doc A chunks preserved in DB ({chunk_a_count} row) : {'✓ PASS' if chunks_preserved else '✗ FAIL'}")

        # Cleanup test company and documents
        await db.delete(chunk_b)
        await db.delete(chunk_a)
        await db.delete(doc_b)
        await db.delete(doc_a)
        await db.delete(test_company)
        await db.commit()
        print("\n  Cleanup: Removed test company and test document rows.")

        all_passed = b_included and a_excluded and is_inactive_in_db and chunks_preserved
        print(f"\nFINAL TEST RESULT: {'✓ ALL CHECKS PASSED' if all_passed else '✗ TEST FAILED'}")
        print("=" * 70 + "\n")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_test())
