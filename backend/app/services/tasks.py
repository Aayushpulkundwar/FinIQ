import asyncio
import os
import re
from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.repositories.document import DocumentRepository
from app.repositories.document_chunk import DocumentChunkRepository
from app.models.document import ProcessingStatus
from app.services.storage import StorageService
from app.rag.parsers.pdf import PDFParser
from app.rag.parsers.docx import DocxParser
from app.rag.parsers.pptx import PptxParser
from app.rag.cleaner import TextCleaner
from app.rag.chunker import DocumentChunker
from app.rag.embeddings import EmbeddingService
from app.services.news_intelligence import NewsIntelligenceService
from app.services.market_intelligence import MarketIntelligenceService
from loguru import logger



async def mark_document_failed(document_id: str):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.core.config import settings
    from app.repositories.document import DocumentRepository
    from app.models.document import ProcessingStatus

    local_engine = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URI,
        echo=False,
        future=True,
    )
    LocalSessionLocal = async_sessionmaker(
        bind=local_engine,
        class_=AsyncSession,
    )
    try:
        async with LocalSessionLocal() as db:
            doc_repo = DocumentRepository(db)
            doc = await doc_repo.get(id=document_id)
            if doc:
                doc.processing_status = ProcessingStatus.failed
                await doc_repo.update(db_obj=doc, obj_in={})
                await db.commit()
    finally:
        await local_engine.dispose()


@celery_app.task(name="app.services.tasks.process_document")
def process_document_task(document_id: str):
    """
    Celery task entrypoint for background document processing.
    Executes the async business logic inside a running event loop.
    """
    logger.info(f"Background task triggered for document {document_id}")
    try:
        asyncio.run(process_document(document_id))
    except Exception as exc:
        logger.error(f"Fatal error in process_document_task for {document_id}: {exc}")
        try:
            asyncio.run(mark_document_failed(document_id))
        except Exception as fallback_err:
            logger.error(f"Failed to mark document {document_id} as failed in fallback: {fallback_err}")
        raise exc


async def process_document(document_id: str):
    """
    Runs the full RAG Ingestion Pipeline:
    1. Downloads file from MinIO.
    2. Identifies file type and parses text page-by-page.
    3. Cleans extracted text.
    4. Splits text into configurable chunks with overlap.
    5. Generates OpenAI vector embeddings.
    6. Stores chunk texts and vectors in PostgreSQL using pgvector.
    7. Updates document processing status.
    """
    logger.bind(document_id=document_id).info("RAG ingestion pipeline started.")

    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.core.config import settings

    local_engine = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URI,
        echo=False,
        future=True,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
    )
    LocalSessionLocal = async_sessionmaker(
        bind=local_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    try:
        async with LocalSessionLocal() as db:
            doc_repo = DocumentRepository(db)
            doc = await doc_repo.get(id=document_id)
            if not doc:
                logger.bind(document_id=document_id).error("Document not found in database.")
                return

            # Update status to processing
            doc.processing_status = ProcessingStatus.processing
            await doc_repo.update(db_obj=doc, obj_in={})
            await db.commit()

            # Delete any existing chunks for this document to ensure idempotent re-ingestion
            from app.models.document_chunk import DocumentChunk
            from sqlalchemy import delete
            stmt = delete(DocumentChunk).where(DocumentChunk.document_id == doc.id)
            await db.execute(stmt)
            await db.commit()
 
            try:
                # 1. Download file from MinIO
                storage = StorageService()
                file_bytes = storage.download_file(doc.file_path)

                # 2. Select parser based on file extension
                _, ext = os.path.splitext(doc.file_name.lower())
                if ext == ".pdf":
                    parser = PDFParser()
                elif ext == ".docx":
                    parser = DocxParser()
                elif ext == ".pptx":
                    parser = PptxParser()
                else:
                    raise ValueError(f"Unsupported file type extension: {ext}")

                raw_pages = parser.parse(file_bytes)

                # 3. Clean text
                cleaned_pages = []
                for page in raw_pages:
                    cleaned_text = TextCleaner.clean(page.get("text", ""))
                    cleaned_pages.append({
                        "text": cleaned_text,
                        "page_number": page.get("page_number", 1),
                        "section_title": page.get("section_title"),
                        "tables": page.get("tables", [])
                    })

                # 4. Chunk text
                raw_chunks = DocumentChunker.chunk_document(
                    pages=cleaned_pages,
                    document_id=doc.id,
                    company_id=doc.company_id,
                    document_type=doc.document_type.value,
                    fiscal_year=doc.fiscal_year,
                )

                # Append structured table chunks separately
                for page in cleaned_pages:
                    for table_md in page.get("tables", []):
                        import hashlib
                        # Compute unique hash
                        norm_text = re.sub(r"\s+", "", table_md.lower())
                        chunk_hash = hashlib.md5(norm_text.encode("utf-8")).hexdigest()
                        
                        raw_chunks.append({
                            "document_id": doc.id,
                            "chunk_text": table_md,
                            "metadata": {
                                "document_id": str(doc.id),
                                "company_id": str(doc.company_id),
                                "page_number": page.get("page_number", 1),
                                "chunk_index": len(raw_chunks),
                                "document_type": doc.document_type.value,
                                "fiscal_year": doc.fiscal_year,
                                "section_title": page.get("section_title") or "Financial Tables",
                                "statement_type": "table",
                                "section_type": "financial_statements",
                                "business_segments": [],
                                "file_hash": chunk_hash
                            }
                        })

                # 5. Generate embeddings and store if chunks exist
                if not raw_chunks:
                    logger.bind(document_id=document_id).warning("No text chunks extracted from document.")
                else:
                    embedder = EmbeddingService()
                    chunk_texts = [c["chunk_text"] for c in raw_chunks]
                    embeddings = embedder.get_embeddings(chunk_texts)

                    # Store vectors and chunk text
                    from app.models.document_chunk import DocumentChunk
                    is_mock = embedder.is_mock_mode
                    for chunk_idx, raw_chunk in enumerate(raw_chunks):
                        meta = raw_chunk["metadata"]
                        chunk_obj = DocumentChunk(
                            document_id=raw_chunk["document_id"],
                            company_id=doc.company_id,
                            chunk_text=raw_chunk["chunk_text"],
                            embedding=embeddings[chunk_idx],
                            page_number=meta["page_number"],
                            chunk_index=meta["chunk_index"],
                            document_type=doc.document_type,
                            fiscal_year=doc.fiscal_year,
                            section_title=meta.get("section_title"),
                            metadata_json=meta,
                            is_mock_embedding=is_mock
                        )
                        db.add(chunk_obj)

                    await db.flush()

                # Update status to completed
                doc.processing_status = ProcessingStatus.completed
                await doc_repo.update(db_obj=doc, obj_in={})
                await db.commit()
                logger.bind(document_id=document_id).info("RAG ingestion pipeline completed successfully.")

            except ValueError as ve:
                logger.bind(document_id=document_id).error(f"RAG pipeline ingestion failed due to misconfiguration: {ve}")
                # Mark document processing as failed
                doc.processing_status = ProcessingStatus.failed
                await doc_repo.update(db_obj=doc, obj_in={})
                await db.commit()
                raise ve
            except Exception as e:
                is_quota_exhausted = "429" in str(e) or "quota" in str(e).lower() or "limit" in str(e).lower() or "exhausted" in str(e).lower()
                if is_quota_exhausted:
                    logger.bind(document_id=document_id).error(f"RAG pipeline ingestion failed due to transient quota exhaustion: {e}")
                else:
                    logger.bind(document_id=document_id).error(f"RAG pipeline ingestion failed due to unexpected error: {e}")
                # Mark document processing as failed
                doc.processing_status = ProcessingStatus.failed
                await doc_repo.update(db_obj=doc, obj_in={})
                await db.commit()
                raise e
    finally:
        await local_engine.dispose()


@celery_app.task(name="app.services.tasks.process_news")
def process_news_task(news_payload: dict):
    """
    Celery task entrypoint for background news ingestion and market event correlation.
    """
    logger.info("Background news processing task triggered.")
    try:
        asyncio.run(process_news(news_payload))
    except Exception as exc:
        logger.error(f"Fatal error in process_news_task: {exc}")
        raise exc


async def process_news(news_payload: dict):
    """
    Asynchronously processes the ingested news:
    1. Instantiates NewsIntelligenceService and MarketIntelligenceService.
    2. Runs ingestion.
    3. Triggers market intelligence event correlations.
    """
    from app.schemas.market import NewsIngestionRequest
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.core.config import settings

    local_engine = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URI,
        echo=False,
        future=True,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
    )
    LocalSessionLocal = async_sessionmaker(
        bind=local_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    try:
        async with LocalSessionLocal() as db:
            news_service = NewsIntelligenceService(db)
            market_service = MarketIntelligenceService(db)
            
            # Run ingestion
            req = NewsIngestionRequest(**news_payload)
            ingested = await news_service.ingest_news(req)
            logger.info(f"Asynchronously ingested {len(ingested)} news articles.")
            
            # Automatically trigger event correlations for the ingested articles
            if ingested:
                analysis = await market_service.analyze(limit=20)
                logger.info("Asynchronous market event correlation completed successfully.")
            
            await db.commit()
    except Exception as e:
        logger.error(f"Async news ingestion task failed: {e}")
        raise e
    finally:
        await local_engine.dispose()


@celery_app.task(bind=True, name="app.services.tasks.run_investment_analysis")
def run_investment_analysis_task(self, company_id: str, fiscal_year: int):
    """
    Celery task wrapper for running async investment analysis.
    """
    logger.info(f"Background investment analysis task triggered for company {company_id}, FY {fiscal_year}")
    try:
        return asyncio.run(run_investment_analysis_async(self, company_id, fiscal_year))
    except Exception as exc:
        logger.error(f"Fatal error in run_investment_analysis_task: {exc}")
        raise exc


async def run_investment_analysis_async(self, company_id: str, fiscal_year: int) -> dict:
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.core.config import settings
    from app.services.valuation import ValuationService
    from app.services.research_report import ResearchReportService
    from uuid import UUID

    co_uuid = UUID(company_id)

    local_engine = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URI,
        echo=False,
        future=True,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
    )
    LocalSessionLocal = async_sessionmaker(
        bind=local_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    try:
        async with LocalSessionLocal() as db:
            # Step 1: Calculate WACC, DCF, and Sensitivity analysis
            self.update_state(state="PROGRESS", meta={"message": "Calculating DCF valuation and WACC..."})
            valuation_service = ValuationService(db)
            valuation = await valuation_service.calculate_valuation(
                company_id=co_uuid,
                fiscal_year=fiscal_year
            )

            # Step 2: Retrieve context & generate consolidated report
            self.update_state(state="PROGRESS", meta={"message": "Retrieving company filing contexts..."})
            report_service = ResearchReportService(db)
            
            # Step 3: Run report generation (which calls response generator)
            self.update_state(state="PROGRESS", meta={"message": "Generating institutional research report..."})
            report_markdown = await report_service.generate_report(
                company_id=co_uuid,
                fiscal_year=fiscal_year
            )

            # Build final response payload
            company_name = report_markdown.split("\n")[0].replace("# INVESTMENT RESEARCH REPORT:", "").strip()
            valuation_dict = valuation.model_dump()

            return {
                "company_id": company_id,
                "company_name": company_name,
                "valuation_summary": valuation_dict,
                "intrinsic_value": valuation.dcf_details.intrinsic_share_price,
                "sensitivity_analysis": valuation_dict["sensitivity_grid"],
                "research_report": report_markdown
            }
    finally:
        await local_engine.dispose()


