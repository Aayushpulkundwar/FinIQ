import asyncio
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.document import Document
from app.models.company import Company

async def check_paths():
    db = SessionLocal()
    try:
        stmt = select(Document, Company.company_name).join(Company, Company.id == Document.company_id)
        rows = (await db.execute(stmt)).all()
        print(f"TOTAL DOCUMENTS IN DB: {len(rows)}\n")
        for doc, comp in rows:
            print(f"Company: {comp}")
            print(f"  Company ID: {doc.company_id}")
            print(f"  File Name : {doc.file_name}")
            print(f"  File Path : {doc.file_path}")
            print(f"  File Hash : {doc.file_hash}")
            print("-" * 70)
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(check_paths())
