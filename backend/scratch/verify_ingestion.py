import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings

async def verify_db():
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    session_maker = async_sessionmaker(engine)
    async with session_maker() as session:
        # Total chunks and mock chunk flags
        res = await session.execute(text(
            "SELECT COUNT(*), SUM(CASE WHEN is_mock_embedding THEN 1 ELSE 0 END) "
            "FROM document_chunks "
            "WHERE document_id = '1d891cb3-1d37-4945-9f13-60621fa57ab5'"
        ))
        row = res.fetchone()
        print('Total chunks in DB:', row[0])
        print('Mock chunks flag count:', row[1])
        
        # Check if there are any zero vectors (all elements zero)
        res2 = await session.execute(text(
            "SELECT COUNT(*) FROM document_chunks "
            "WHERE document_id = '1d891cb3-1d37-4945-9f13-60621fa57ab5' "
            "AND embedding = array_fill(0.0, ARRAY[1536])::vector(1536)"
        ))
        print('Zero-vector count:', res2.scalar())
        
        # Check vector dimension
        res3 = await session.execute(text(
            "SELECT vector_dims(embedding) FROM document_chunks "
            "WHERE document_id = '1d891cb3-1d37-4945-9f13-60621fa57ab5' LIMIT 1"
        ))
        print('Vector dimensions:', res3.scalar())

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(verify_db())
