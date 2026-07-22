import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings

async def update_status():
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    session_maker = async_sessionmaker(engine)
    async with session_maker() as session:
        await session.execute(text(
            "UPDATE documents SET processing_status = 'completed' "
            "WHERE id = '1d891cb3-1d37-4945-9f13-60621fa57ab5'"
        ))
        await session.commit()
        print("VRLLOG status set to completed in database.")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(update_status())
