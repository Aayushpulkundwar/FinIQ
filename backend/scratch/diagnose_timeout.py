import sys
import os
import time
import asyncio
from uuid import UUID
from sqlalchemy import select

# Add parent directory to path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.models.company import Company
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.financial_intelligence.service import FinancialIntelligenceService
from app.services.valuation import ValuationService
from app.services.retrieval import RetrievalService
from app.services.response_generation import ResponseGenerationService

async def diagnose():
    db = SessionLocal()
    try:
        # Get all companies
        comp_res = await db.execute(select(Company))
        companies = comp_res.scalars().all()
        
        print("=== DATABASE METRICS BY COMPANY ===")
        tvsscs_id = None
        for c in companies:
            doc_res = await db.execute(select(Document).where(Document.company_id == c.id))
            docs = doc_res.scalars().all()
            doc_ids = [d.id for d in docs]
            
            chunk_count = 0
            if doc_ids:
                chunk_res = await db.execute(select(DocumentChunk).where(DocumentChunk.document_id.in_(doc_ids)))
                chunks = chunk_res.scalars().all()
                chunk_count = len(chunks)
                
            print(f"Company: {c.company_name} ({c.ticker_symbol}) | ID: {c.id}")
            print(f"  - Documents: {len(docs)}")
            print(f"  - Chunks: {chunk_count}")
            
            if "TVS" in c.company_name or c.ticker_symbol == "TVSSCS":
                tvsscs_id = c.id
                
        if not tvsscs_id:
            print("\nERROR: Could not find TVS Supply Chain Solutions Ltd in database.")
            return

        print(f"\n=== PROFILING ANALYSIS PIPELINE FOR TVSSCS (ID: {tvsscs_id}) ===")
        
        # 1. Financial Service
        print("\nStep 1: Running FinancialIntelligenceService.analyze...")
        fin_service = FinancialIntelligenceService(db)
        start = time.perf_counter()
        try:
            fin_data = await fin_service.analyze(tvsscs_id, fiscal_year=2026)
            duration = time.perf_counter() - start
            print(f"  -> SUCCESS in {duration:.2f} seconds.")
            print(f"  -> Financial Evidence Count: {len(fin_data.financial_evidence)}")
        except Exception as e:
            duration = time.perf_counter() - start
            print(f"  -> FAILED in {duration:.2f} seconds. Error: {e}")
            fin_data = None
            
        # 2. Valuation Service
        print("\nStep 2: Running ValuationService.calculate_valuation...")
        val_service = ValuationService(db)
        start = time.perf_counter()
        try:
            val_data = await val_service.calculate_valuation(tvsscs_id, fiscal_year=2026)
            duration = time.perf_counter() - start
            print(f"  -> SUCCESS in {duration:.2f} seconds.")
            print(f"  -> Intrinsic Share Price: {val_data.dcf_details.intrinsic_share_price if val_data and val_data.dcf_details else 'N/A'}")
        except Exception as e:
            duration = time.perf_counter() - start
            print(f"  -> FAILED in {duration:.2f} seconds. Error: {e}")
            val_data = None
            
        # 3. Retrieval Service
        print("\nStep 3: Running RetrievalService.search (Ollama Embeddings)...")
        ret_service = RetrievalService(db)
        start = time.perf_counter()
        try:
            text_chunks = await ret_service.search(
                query="business model overview competition risks industry opportunities",
                top_k=8,
                company_id=tvsscs_id
            )
            duration = time.perf_counter() - start
            print(f"  -> SUCCESS in {duration:.2f} seconds.")
            print(f"  -> Retrieved Chunks: {len(text_chunks)}")
        except Exception as e:
            duration = time.perf_counter() - start
            print(f"  -> FAILED in {duration:.2f} seconds. Error: {e}")
            text_chunks = []
            
        # 4. Response Generator (OpenRouter)
        print("\nStep 4: Running ResponseGenerationService.generate_response (OpenRouter)...")
        resp_gen = ResponseGenerationService()
        
        # Prepare context data
        company = next(c for c in companies if c.id == tvsscs_id)
        company_dict = {
            "company_name": company.company_name,
            "ticker_symbol": company.ticker_symbol,
            "exchange": company.exchange,
            "sector": company.sector,
            "industry": company.industry,
        }
        retrieved_chunks = []
        if fin_data:
            for ev in fin_data.financial_evidence:
                if ev.chunk_text:
                    retrieved_chunks.append({
                        "chunk_text": ev.chunk_text,
                        "document_title": ev.document_title,
                        "page_number": ev.page_number,
                        "section_title": ev.section_title,
                        "similarity_score": ev.similarity_score,
                    })
        for chunk in text_chunks:
            retrieved_chunks.append({
                "chunk_text": chunk.chunk_text,
                "document_title": chunk.document_title,
                "page_number": chunk.page_number,
                "section_title": chunk.section_title,
                "similarity_score": float(chunk.similarity_score),
            })
            
        user_query = (
            f"Generate a comprehensive, institutional-quality investment research report for {company.company_name} ({company.ticker_symbol}). "
            f"Format into standard sections: Executive Summary, Company Overview, Business Model, Industry Analysis, "
            f"Financial Performance, Financial Ratios, Event Intelligence Summary, Valuation Summary, Key Risks, "
            f"Opportunities, Investment Thesis, Conclusion, Supporting Evidence."
        )
        
        start = time.perf_counter()
        try:
            ai_resp = await resp_gen.generate_response(
                user_query=user_query,
                company_details=company_dict,
                document_metadata=[],
                retrieved_chunks=retrieved_chunks,
            )
            duration = time.perf_counter() - start
            print(f"  -> SUCCESS in {duration:.2f} seconds.")
            print(f"  -> Executive Summary Length: {len(ai_resp.executive_summary) if ai_resp else 0} chars")
            print(f"  -> Is Degraded: {ai_resp.is_degraded if ai_resp else 'N/A'}")
            print(f"  -> Error Message: {ai_resp.error_message if ai_resp else 'N/A'}")
        except Exception as e:
            duration = time.perf_counter() - start
            print(f"  -> FAILED in {duration:.2f} seconds. Error: {e}")

    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(diagnose())
