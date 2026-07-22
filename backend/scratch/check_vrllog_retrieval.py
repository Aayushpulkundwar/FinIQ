import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
from app.models.company import Company
from app.api.v1.routers.chat import query_orchestrator
from app.schemas.chat import ChatQueryRequest
from app.services.chat_history_service import ChatHistoryService

async def test_vrllog_chat():
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    session_maker = async_sessionmaker(engine)
    async with session_maker() as session:
        # Fetch VRL Logistics company
        res = await session.execute(select(Company).where(Company.ticker_symbol == "VRLLOG"))
        company = res.scalars().first()
        if not company:
            print("Company VRLLOG not found!")
            return
            
        target_company_id = str(company.id)
        print(f"Testing VRLLOG Chat - Company: {company.company_name} (ID: {target_company_id})")
        
        # Create a chat session bound to VRLLOG
        history_service = ChatHistoryService(session)
        chat_sess = await history_service.create_session(ticker="VRLLOG")
        print(f"Created chat session: {chat_sess.id}")
        # Query about VRL Logistics operations
        payload = ChatQueryRequest(
            query="What are the key risks or business operations details discussed in the VRL Logistics report?",
            session_id=chat_sess.id
        )
        
        print(f"Sending query: '{payload.query}'...")
        response = await query_orchestrator(payload, session)
        
        print("\n--- Response Summary ---")
        print("Executive Summary:", response.response.executive_summary[:300] + "...")
        print("Number of retrieved chunks:", len(response.retrieved_chunks))
        
        # Check source documents of retrieved chunks
        all_vrl = True
        for idx, chunk in enumerate(response.retrieved_chunks):
            doc_title = chunk.get("document_title", "Unnamed")
            company_id = chunk.get("company_id")
            print(f"Chunk {idx}: Title='{doc_title}', CompanyID={company_id}")
            if str(company_id) != target_company_id:
                all_vrl = False
                
        if all_vrl and len(response.retrieved_chunks) > 0:
            print("\nSUCCESS: All retrieved chunks belong exclusively to VRL Logistics!")
        else:
            print("\nFAILURE: Some retrieved chunks belong to another company or no chunks were retrieved.")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test_vrllog_chat())
