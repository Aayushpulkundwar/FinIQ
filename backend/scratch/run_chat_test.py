import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
from app.models.company import Company
from app.models.chat import ChatSession
from app.api.v1.routers.chat import query_orchestrator
from app.schemas.chat import ChatQueryRequest
from app.services.chat_history_service import ChatHistoryService

async def run_chat():
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    session_maker = async_sessionmaker(engine)
    async with session_maker() as session:
        # Fetch the company
        res = await session.execute(select(Company).where(Company.ticker_symbol == "ARVIND"))
        company = res.scalars().first()
        if not company:
            print("Company ARVIND not found!")
            return
        
        print(f"Found company: {company.company_name} (Ticker: {company.ticker_symbol})")
        
        # Create a chat session bound to ARVIND
        history_service = ChatHistoryService(session)
        chat_sess = await history_service.create_session(ticker="ARVIND")
        print(f"Created chat session: {chat_sess.id}")
        
        # Construct ChatQueryRequest
        # Note: We ask a RAG-dependent query about Arvind's performance / segments
        payload = ChatQueryRequest(
            query="Summarize the retail and textile segment performance for Arvind Limited from their annual report.",
            session_id=chat_sess.id
        )
        
        print(f"Sending query: '{payload.query}'...")
        response = await query_orchestrator(payload, session)
        
        print("\n--- Response Received ---")
        print("Executive Summary:", response.response.executive_summary)
        print("Provider used:", response.response.provider)
        print("Key Insights:", response.response.key_insights)
        print("Number of retrieved chunks:", len(response.retrieved_chunks))
        
        for idx, chunk in enumerate(response.retrieved_chunks[:3]):
            print(f"Chunk {idx}: text snippet: {chunk.get('chunk_text')[:100]}...")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_chat())
