import asyncio
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.document import Document
from app.models.document_chunk import DocumentChunk

async def check():
    db = SessionLocal()
    try:
        companies_stmt = select(Company)
        companies_res = await db.execute(companies_stmt)
        companies = companies_res.scalars().all()
        print(f"COMPANIES_COUNT: {len(companies)}")
        for c in companies:
            print(f"COMPANY: {c.company_name} ({c.ticker_symbol}) id={c.id}")
            
        docs_stmt = select(Document)
        docs_res = await db.execute(docs_stmt)
        docs = docs_res.scalars().all()
        print(f"DOCUMENTS_COUNT: {len(docs)}")
        for d in docs:
            print(f"DOCUMENT: {d.title} id={d.id} company_id={d.company_id}")
            
        chunks_stmt = select(DocumentChunk)
        chunks_res = await db.execute(chunks_stmt)
        chunks = chunks_res.scalars().all()
        print(f"CHUNKS_COUNT: {len(chunks)}")
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(check())
