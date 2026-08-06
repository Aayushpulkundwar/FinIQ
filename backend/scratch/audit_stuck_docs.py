import asyncio
from sqlalchemy import select, func
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.document import Document
from app.models.document_chunk import DocumentChunk

async def audit_docs():
    db = SessionLocal()
    try:
        stmt = select(Document, Company.company_name, Company.ticker_symbol)\
            .join(Company, Company.id == Document.company_id)
        res = await db.execute(stmt)
        rows = res.all()
        
        print(f"TOTAL DOCUMENTS IN DB: {len(rows)}\n")
        print(f"{'Company':<35} | {'Doc ID':<36} | {'Proc Status':<12} | {'Up Status':<10} | {'Chunks in DB':<12} | {'Updated At'}")
        print("-" * 130)
        
        for doc, company_name, ticker in rows:
            chunk_stmt = select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == doc.id)
            chunk_res = await db.execute(chunk_stmt)
            actual_chunks = chunk_res.scalar() or 0
            
            print(f"{company_name} ({ticker}) | {doc.id} | {doc.processing_status.value:<12} | {doc.upload_status.value:<10} | {actual_chunks:<12} | {doc.updated_at}")
            
    except Exception as e:
        print(f"Error querying DB: {e}")
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(audit_docs())
