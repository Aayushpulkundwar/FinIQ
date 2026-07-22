import asyncio
import json
import os
import sys
from sqlalchemy import select, func
from loguru import logger

# Add current folder to sys.path to allow imports
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.models.company import Company
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.retrieval import RetrievalService
from app.services.response_generation import (
    ResponseGenerationService,
    get_llm_model,
    clean_and_parse_json
)
from app.core.config import settings
from app.ai.prompts.research import INVESTMENT_RESEARCH_PROMPT
from app.core.cache import json_serial
from app.schemas.response_generation import AIResponse

async def main():
    logger.info("Standalone Diagnostic Script Started.")
    db = SessionLocal()
    
    report_data = {
        "database_inspection": {},
        "queries_executed": [],
        "overall_status": "PASS"
    }

    # 1. Database Inspection
    try:
        company_stmt = select(Company).where(Company.company_name.ilike("%Arvind Limited%"))
        company_res = await db.execute(company_stmt)
        company = company_res.scalars().first()

        if company:
            company_info = {
                "id": str(company.id),
                "company_name": company.company_name,
                "ticker_symbol": company.ticker_symbol,
                "status": "PASS"
            }
            doc_stmt = select(func.count(Document.id)).where(Document.company_id == company.id)
            doc_res = await db.execute(doc_stmt)
            doc_count = doc_res.scalar() or 0

            chunk_stmt = select(func.count(DocumentChunk.id)).where(DocumentChunk.company_id == company.id)
            chunk_res = await db.execute(chunk_stmt)
            chunk_count = chunk_res.scalar() or 0

            emb_stmt = select(func.count(DocumentChunk.id)).where(
                DocumentChunk.company_id == company.id,
                DocumentChunk.embedding != None
            )
            emb_res = await db.execute(emb_stmt)
            emb_count = emb_res.scalar() or 0

            company_info.update({
                "documents_indexed": doc_count,
                "chunks_indexed": chunk_count,
                "embeddings_created": emb_count,
            })
        else:
            company_info = {
                "id": None,
                "company_name": "Arvind Limited",
                "ticker_symbol": "ARVIND",
                "status": "FAIL",
                "reason": "Company 'Arvind Limited' not found in database.",
                "documents_indexed": 0,
                "chunks_indexed": 0,
                "embeddings_created": 0,
            }
            report_data["overall_status"] = "FAIL"

        report_data["database_inspection"] = company_info

    except Exception as e:
        logger.error(f"Database inspection failed: {e}")
        report_data["database_inspection"] = {
            "status": "FAIL",
            "reason": f"Database query exception: {str(e)}"
        }
        report_data["overall_status"] = "FAIL"
        company = None

    # 2. Execute Test Cases
    test_queries = [
        "What does Arvind Limited do?",
        "Which industry does Arvind Limited operate in?",
        "Summarize the Chairman's message.",
        "What are the company's key risks?",
        "What were the FY2025 financial highlights?"
    ]

    retrieval_service = RetrievalService(db)
    response_service = ResponseGenerationService()

    for query in test_queries:
        logger.info(f"Executing pipeline check for query: '{query}'")
        q_trace = {
            "query": query,
            "company_resolved": "Arvind Limited" if company else "None",
            "company_id": str(company.id) if company else None,
            "pipeline_stages": {
                "company_resolution": "PASS" if company else "FAIL",
                "retrieval": "FAIL",
                "llm_generation": "FAIL",
                "json_parsing": "FAIL"
            },
            "retrieved_chunks": [],
            "prompt_sent": "Not Formatted",
            "raw_response": "",
            "final_ai_response": None
        }

        if not company:
            report_data["queries_executed"].append(q_trace)
            continue

        try:
            # 2a. Retrieval
            chunks = await retrieval_service.search(query=query, company_id=company.id, top_k=5)
            q_trace["pipeline_stages"]["retrieval"] = "PASS" if len(chunks) > 0 else "WARNING (No chunks retrieved)"
            
            for c in chunks:
                q_trace["retrieved_chunks"].append({
                    "document_title": c.document_title,
                    "page_number": c.page_number,
                    "section_title": c.section_title or "No Section",
                    "similarity_score": float(c.similarity_score),
                    "text_snippet": c.chunk_text[:300] + "..." if len(c.chunk_text) > 300 else c.chunk_text
                })

            # 2b. Formulate prompt
            search_matches = ""
            for idx, chunk in enumerate(chunks):
                title = chunk.document_title or "Unnamed Document"
                page = chunk.page_number or 1
                text = chunk.chunk_text or ""
                search_matches += f"Chunk {idx+1}:\nText: {text}\nSource: {title}, Page {page}\n\n"

            messages = INVESTMENT_RESEARCH_PROMPT.format_messages(
                query=query,
                company_details=json.dumps({
                    "id": str(company.id),
                    "company_name": company.company_name,
                    "ticker_symbol": company.ticker_symbol
                }, default=json_serial),
                document_metadata=json.dumps([], default=json_serial),
                search_matches=search_matches
            )
            q_trace["prompt_sent"] = "\n".join([f"{msg.type.upper()}: {msg.content}" for msg in messages])

            # 2c. LLM / Fallback
            if settings.ALLOW_MOCK_LLM or not chunks:
                ai_res = await response_service._generate_fallback(
                    user_query=query,
                    company_details={
                        "id": str(company.id),
                        "company_name": company.company_name,
                        "ticker_symbol": company.ticker_symbol
                    },
                    retrieved_chunks=[c.model_dump() for c in chunks],
                    cache_key=f"diagnostic_cache_key:{query}"
                )
                q_trace["raw_response"] = "Mock Fallback Generator executed because ALLOW_MOCK_LLM=True or retrieved chunks is empty."
                q_trace["pipeline_stages"]["llm_generation"] = "PASS (Mocked)"
                q_trace["pipeline_stages"]["json_parsing"] = "PASS"
                q_trace["final_ai_response"] = ai_res.model_dump()
            else:
                llm = get_llm_model(settings.LLM_PROVIDER)
                from app.core.circuit_breaker import get_circuit_breaker
                breaker = get_circuit_breaker(f"{settings.LLM_PROVIDER}_chat_api")
                response = await breaker.call(llm.ainvoke, messages)
                
                content = response.content.strip()
                q_trace["raw_response"] = content
                q_trace["pipeline_stages"]["llm_generation"] = "PASS"

                try:
                    parsed = clean_and_parse_json(content)
                    ai_res = AIResponse(
                        executive_summary=parsed.get("executive_summary") or parsed.get("summary") or "Summary not generated.",
                        key_insights=parsed.get("key_insights") or [],
                        supporting_evidence=parsed.get("supporting_evidence") or [],
                        risks_limitations=parsed.get("risks_limitations") or [],
                        sources=parsed.get("sources") or []
                    )
                    q_trace["pipeline_stages"]["json_parsing"] = "PASS"
                    q_trace["final_ai_response"] = ai_res.model_dump()
                except Exception as parse_err:
                    logger.error(f"JSON parse failed: {parse_err}")
                    q_trace["pipeline_stages"]["json_parsing"] = f"FAIL ({str(parse_err)})"
                    report_data["overall_status"] = "FAIL"

        except Exception as query_err:
            logger.error(f"Query execution failed: {query_err}")
            q_trace["pipeline_stages"]["llm_generation"] = f"FAIL ({str(query_err)})"
            report_data["overall_status"] = "FAIL"

        report_data["queries_executed"].append(q_trace)

    # 3. Format and write Markdown Report
    try:
        report_md = f"""# RAG Pipeline Diagnostic & Verification Report

**Status**: {report_data["overall_status"]}
**LLM Provider**: {settings.LLM_PROVIDER}
**LLM Model**: {settings.GEMINI_MODEL}
**Mock Mode (ALLOW_MOCK_LLM)**: {settings.ALLOW_MOCK_LLM}

## 1. Database Ingest & In-Memory Records
- **Company Name**: {report_data["database_inspection"].get("company_name")}
- **Ticker Symbol**: {report_data["database_inspection"].get("ticker_symbol")}
- **Company Profile Ingest**: {report_data["database_inspection"].get("status")}
- **Documents Indexed**: {report_data["database_inspection"].get("documents_indexed", 0)}
- **Chunks Generated**: {report_data["database_inspection"].get("chunks_indexed", 0)}
- **Embeddings Created**: {report_data["database_inspection"].get("embeddings_created", 0)}

---

## 2. Query Pipeline Execution Results
"""

        for q in report_data["queries_executed"]:
            stages = q["pipeline_stages"]
            chunks_log = ""
            for idx, c in enumerate(q["retrieved_chunks"]):
                chunks_log += f"""
#### Chunk {idx+1} (Score: {c["similarity_score"]:.4f})
- **Document**: {c["document_title"]}, Page {c["page_number"]}
- **Section**: {c["section_title"]}
- **Text Snippet**:
  > {c["text_snippet"]}
"""

            report_md += f"""
### Query: "{q["query"]}"
- **Company Resolved**: {q["company_resolved"]}
- **Resolution Status**: {stages["company_resolution"]}
- **Retrieval Status**: {stages["retrieval"]}
- **LLM Gen Status**: {stages["llm_generation"]}
- **JSON Parsing**: {stages["json_parsing"]}

#### Retrieved Chunks ({len(q["retrieved_chunks"])})
{chunks_log if q["retrieved_chunks"] else "No chunks retrieved."}

#### Formatted Prompt
```text
{q["prompt_sent"][:1000] + "..." if len(q["prompt_sent"]) > 1000 else q["prompt_sent"]}
```

#### Raw LLM Response
```text
{q["raw_response"]}
```

#### Final parsed AIResponse Schema
```json
{json.dumps(q["final_ai_response"], indent=2) if q["final_ai_response"] else "Failed to compile."}
```
---
"""

        report_path = os.path.join(os.getcwd(), "diagnostic_report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_md)
        print(f"\nDIAGNOSTIC COMPLETED: Report successfully written to local path: {report_path}\n")
    except Exception as report_err:
        print(f"\nDIAGNOSTIC ERROR: Failed to compile markdown report: {report_err}\n")

    await db.close()

if __name__ == "__main__":
    import traceback
    try:
        asyncio.run(main())
    except Exception as err:
        error_path = os.path.join(os.getcwd(), "diagnostic_error.txt")
        with open(error_path, "w", encoding="utf-8") as f:
            f.write("STANDALONE RUNTIME ERROR:\n")
            f.write(str(err) + "\n")
            f.write(traceback.format_exc() + "\n")
        print(f"CRITICAL: Standalone script failed. Traceback written to: {error_path}")
