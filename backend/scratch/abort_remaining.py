import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings

async def abort_remaining():
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    session_maker = async_sessionmaker(engine)
    async with session_maker() as session:
        # Update processing_status to failed for the remaining 2 documents
        res = await session.execute(text(
            "UPDATE documents SET processing_status = 'failed' "
            "WHERE id IN ('5b1b3b7b-835c-4c9b-9947-4471f85f0041', 'aa6c62fd-a8d7-43b1-b4d5-e994df038986')"
        ))
        await session.commit()
        print(f"Status reset committed! Rows updated: {res.rowcount}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(abort_remaining())
