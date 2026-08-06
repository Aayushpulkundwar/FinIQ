import asyncio
from sqlalchemy import select, func
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.document import Document
from app.models.document_chunk import DocumentChunk

async def check_all_companies():
    db = SessionLocal()
    try:
        res = await db.execute(select(Company))
        companies = res.scalars().all()
        print(f"Total Companies in DB: {len(companies)}")
        for c in companies:
            doc_stmt = select(Document).where(Document.company_id == c.id)
            docs = (await db.execute(doc_stmt)).scalars().all()
            print(f"- Company: {c.company_name} (ID: {c.id}, Ticker: {c.ticker_symbol}) -> {len(docs)} documents")
            for d in docs:
                cnt_stmt = select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == d.id)
                cnt = (await db.execute(cnt_stmt)).scalar()
                print(f"    * Doc: {d.file_name} (ID: {d.id}) | Proc Status: {d.processing_status.value} | Chunks: {cnt}")
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(check_all_companies())
