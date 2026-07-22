import asyncio
import sys
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
from app.models.document import Document, ProcessingStatus
from app.models.document_chunk import DocumentChunk

async def run():
    confirm = "--confirm" in sys.argv
    print(f"Starting mock chunks deletion script (dry-run={not confirm})...")

    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    doc_ids = [
        "1d891cb3-1d37-4945-9f13-60621fa57ab5",
        "5b1b3b7b-835c-4c9b-9947-4471f85f0041",
        "aa6c62fd-a8d7-43b1-b4d5-e994df038986"
    ]

    async with session_maker() as session:
        # 1. Summary of chunks to be deleted
        print("\n--- Summary of mock chunks to be deleted ---")
        to_delete_counts = {}
        for doc_id in doc_ids:
            # Query document title
            res_doc = await session.execute(select(Document).where(Document.id == doc_id))
            doc = res_doc.scalar_one_or_none()
            doc_title = doc.title if doc else "Unknown"

            # Query count of mock chunks
            query_count = text("""
                SELECT COUNT(*) FROM document_chunks 
                WHERE document_id = :doc_id AND is_mock_embedding = TRUE
            """)
            res_count = await session.execute(query_count, {"doc_id": doc_id})
            count = res_count.scalar() or 0
            to_delete_counts[doc_id] = count
            print(f"Document ID: {doc_id} | Title: {doc_title} | Chunks to delete: {count}")

        if not confirm:
            print("\nThis is a DRY-RUN. No changes were made. Use --confirm flag to execute changes.")
            await engine.dispose()
            return

        # 2. Perform deletions and reset document status
        print("\nExecuting mock chunks deletion and document status resets...")
        for doc_id in doc_ids:
            count = to_delete_counts[doc_id]
            if count > 0:
                delete_query = text("""
                    DELETE FROM document_chunks 
                    WHERE document_id = :doc_id AND is_mock_embedding = TRUE
                """)
                res_del = await session.execute(delete_query, {"doc_id": doc_id})
                print(f"Deleted {res_del.rowcount} mock chunks for Document {doc_id}.")
            else:
                print(f"No mock chunks to delete for Document {doc_id}.")

            # Update document status to pending
            res_doc = await session.execute(select(Document).where(Document.id == doc_id))
            doc = res_doc.scalar_one_or_none()
            if doc:
                doc.processing_status = ProcessingStatus.pending
                await session.merge(doc)
                print(f"Reset Document {doc_id} status to pending.")

        await session.commit()
        print("\nTransaction committed successfully!")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run())
