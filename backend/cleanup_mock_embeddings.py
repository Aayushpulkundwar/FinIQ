import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings

async def cleanup():
    print("Connecting to database...")
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_maker() as session:
        print("Scanning for existing zero-vector chunks...")
        # 1. Identify distinct document_ids and counts of all-zero-vector chunks
        query = text("""
            SELECT document_id, COUNT(*) as chunk_count 
            FROM document_chunks 
            WHERE embedding = array_fill(0, ARRAY[1536])::vector
            GROUP BY document_id
        """)
        result = await session.execute(query)
        rows = result.all()

        if not rows:
            print("No zero-vector chunks found in the database. Cleanup complete!")
            await engine.dispose()
            return

        print(f"Found zero-vector chunks for {len(rows)} document(s):")
        total_chunks = 0
        for r in rows:
            doc_id, count = r
            print(f"  - Document ID: {doc_id} | Zero-vector chunks count: {count}")
            total_chunks += count

        # 2. Mark is_mock_embedding = TRUE for these chunks
        print("\nUpdating is_mock_embedding to TRUE for zero-vector chunks...")
        update_query = text("""
            UPDATE document_chunks 
            SET is_mock_embedding = TRUE 
            WHERE embedding = array_fill(0, ARRAY[1536])::vector
        """)
        update_result = await session.execute(update_query)
        await session.commit()
        print(f"Successfully marked {update_result.rowcount} chunks as mock embeddings.")
        print(f"Total zero-vector chunks affected: {total_chunks}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(cleanup())
