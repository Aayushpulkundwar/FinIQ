import asyncio
import os
import re
from uuid import UUID
from datetime import datetime
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


def _make_sync_heartbeat_callback(document_id: UUID):
    """Returns a thread-safe callback updating heartbeat_at in Postgres max once every 10 seconds."""
    from sqlalchemy import create_engine, text
    from app.core.config import settings
    import time
    sync_url = str(settings.DATABASE_URL).replace("+asyncpg", "")
    engine = create_engine(sync_url, pool_pre_ping=True)
    last_update = [0.0]

    def callback(current_page: int, total_pages: int):
        now = time.time()
        if now - last_update[0] >= 10.0:
            last_update[0] = now
            try:
                with engine.connect() as conn:
                    conn.execute(
                        text("UPDATE documents SET heartbeat_at = NOW() WHERE id = :did"),
                        {"did": str(document_id)}
                    )
                    conn.commit()
            except Exception as e:
                logger.warning(f"Heartbeat callback error for doc {document_id}: {e}")

    return callback


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
    Runs the full 5-Stage RAG Ingestion Pipeline with detailed logging:
    STAGE 1: Document Download & MinIO Retrieval
    STAGE 2: Multi-Strategy PDF/Document Parsing & Text Extraction
    STAGE 3: Text Cleaning & Overlapping Chunk Generation
    STAGE 4: Vector Embeddings Generation (bge-m3 via Ollama)
    STAGE 5: PostgreSQL pgvector Batch Insertion & Idempotent Commit
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

            if doc.processing_status == ProcessingStatus.processing:
                logger.bind(document_id=document_id).warning(
                    f"Document {document_id} is already in 'processing' status. Skipping concurrent task trigger."
                )
                return

            # Update status to processing (Atomic lock)
            doc.processing_status = ProcessingStatus.processing
            await doc_repo.update(db_obj=doc, obj_in={})
            await db.commit()

            # Delete any existing chunks for this document to ensure idempotent re-ingestion
            from app.models.document_chunk import DocumentChunk
            from sqlalchemy import delete
            stmt = delete(DocumentChunk).where(DocumentChunk.document_id == doc.id)
            await db.execute(stmt)
            await db.commit()

            temp_path = None
            try:
                from datetime import datetime

                # --- STAGE 1: Download from MinIO ---
                doc.heartbeat_at = datetime.utcnow()
                await doc_repo.update(db_obj=doc, obj_in={})
                await db.commit()

                logger.bind(document_id=document_id).info(
                    f"[STAGE 1/5] Downloading file '{doc.file_name}' ({doc.file_size} bytes) from object path '{doc.file_path}'..."
                )
                import tempfile
                _, ext = os.path.splitext(doc.file_name.lower())
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tf:
                    temp_path = tf.name
                    tf.close()

                storage = StorageService()
                storage.download_file_to_path(doc.file_path, temp_path)
                file_size_on_disk = os.path.getsize(temp_path)
                logger.bind(document_id=document_id).info(
                    f"[STAGE 1/5] MinIO download complete. Saved {file_size_on_disk} bytes to temp path '{temp_path}'."
                )

                # --- STAGE 2: Parse & Extract Text ---
                doc.heartbeat_at = datetime.utcnow()
                await doc_repo.update(db_obj=doc, obj_in={})
                await db.commit()

                logger.bind(document_id=document_id).info(
                    f"[STAGE 2/5] Parsing document extension '{ext}' using multi-strategy parser..."
                )
                hb_cb = _make_sync_heartbeat_callback(document_id)
                if ext == ".pdf":
                    parser = PDFParser()
                    raw_pages = parser.parse(temp_path, progress_callback=hb_cb)
                elif ext == ".docx":
                    parser = DocxParser()
                    raw_pages = parser.parse(temp_path)
                elif ext == ".pptx":
                    parser = PptxParser()
                    raw_pages = parser.parse(temp_path)
                else:
                    raise ValueError(f"Unsupported file type extension: {ext}")
                total_pages_parsed = len(raw_pages)
                total_raw_chars = sum(len(p.get("text", "")) for p in raw_pages)
                non_empty_pages = sum(1 for p in raw_pages if p.get("text", "").strip())
                logger.bind(document_id=document_id).info(
                    f"[STAGE 2/5] Parsing complete. Parsed {total_pages_parsed} pages ({non_empty_pages} non-empty), extracted {total_raw_chars} total characters."
                )

                # --- STAGE 3: Clean & Chunk ---
                doc.heartbeat_at = datetime.utcnow()
                await doc_repo.update(db_obj=doc, obj_in={})
                await db.commit()

                logger.bind(document_id=document_id).info("[STAGE 3/5] Cleaning page text and chunking document...")
                cleaned_pages = []
                for page in raw_pages:
                    cleaned_text = TextCleaner.clean(page.get("text", ""))
                    cleaned_pages.append({
                        "text": cleaned_text,
                        "page_number": page.get("page_number", 1),
                        "section_title": page.get("section_title"),
                        "tables": page.get("tables", [])
                    })

                raw_chunks = DocumentChunker.chunk_document(
                    pages=cleaned_pages,
                    document_id=doc.id,
                    company_id=doc.company_id,
                    document_type=doc.document_type.value,
                    fiscal_year=doc.fiscal_year,
                )
                text_chunk_count = len(raw_chunks)

                # Append structured markdown table chunks separately
                table_chunk_count = 0
                for page in cleaned_pages:
                    for table_md in page.get("tables", []):
                        import hashlib, re
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
                        table_chunk_count += 1

                logger.bind(document_id=document_id).info(
                    f"[STAGE 3/5] Chunking complete. Total chunks={len(raw_chunks)} (Text={text_chunk_count}, Table={table_chunk_count})."
                )

                if not raw_chunks:
                    logger.bind(document_id=document_id).error(
                        f"[STAGE 3/5] Extraction failure: 0 chunks extracted from {total_pages_parsed} pages ({total_raw_chars} chars)."
                    )
                    raise ValueError(
                        f"No text chunks could be extracted from '{doc.file_name}' ({total_pages_parsed} pages, {total_raw_chars} chars)."
                    )

                # --- STAGE 4: Generate Embeddings ---
                doc.heartbeat_at = datetime.utcnow()
                await doc_repo.update(db_obj=doc, obj_in={})
                await db.commit()

                embedder = EmbeddingService()
                is_mock = embedder.is_mock_mode
                INGESTION_BATCH_SIZE = 100
                successfully_flushed_chunks = 0

                logger.bind(document_id=document_id).info(
                    f"[STAGE 4/5] Generating vector embeddings for {len(raw_chunks)} chunks via model='{embedder.embedding_model}' (batch size={INGESTION_BATCH_SIZE})..."
                )

                # --- STAGE 5: Vector DB Insertion ---
                doc.heartbeat_at = datetime.utcnow()
                await doc_repo.update(db_obj=doc, obj_in={})
                await db.commit()
                for i in range(0, len(raw_chunks), INGESTION_BATCH_SIZE):
                    batch_chunks = raw_chunks[i : i + INGESTION_BATCH_SIZE]
                    batch_texts = [c["chunk_text"] for c in batch_chunks]
                    batch_embeddings = embedder.get_embeddings(batch_texts)

                    logger.bind(document_id=document_id).info(
                        f"[STAGE 5/5] Flushing vector batch {i // INGESTION_BATCH_SIZE + 1} ({len(batch_chunks)} chunks) into pgvector..."
                    )

                    try:
                        for chunk_idx, raw_chunk in enumerate(batch_chunks):
                            meta = raw_chunk["metadata"]
                            chunk_obj = DocumentChunk(
                                document_id=raw_chunk["document_id"],
                                company_id=doc.company_id,
                                chunk_text=raw_chunk["chunk_text"],
                                embedding=batch_embeddings[chunk_idx],
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
                        successfully_flushed_chunks += len(batch_chunks)
                    except Exception as batch_err:
                        logger.bind(document_id=document_id).error(
                            f"[STAGE 5/5] Vector DB batch insert failed at chunk index {i}: {batch_err}"
                        )
                        await db.rollback()
                        raise batch_err

                # Completion Guard: Verify all chunks were flushed to pgvector
                if successfully_flushed_chunks != len(raw_chunks) or successfully_flushed_chunks == 0:
                    await db.rollback()
                    raise RuntimeError(
                        f"Chunk insertion mismatch: expected {len(raw_chunks)} chunks, but flushed {successfully_flushed_chunks} chunks."
                    )

                # Update status to completed ONLY after verified vector insertion
                doc.processing_status = ProcessingStatus.completed
                await doc_repo.update(db_obj=doc, obj_in={})
                await db.commit()
                logger.bind(document_id=document_id).info(
                    f"RAG ingestion pipeline completed successfully! Saved {successfully_flushed_chunks} vectors into database."
                )

                # Invalidate financial cache for this company upon completed document ingestion
                try:
                    from app.core.cache import cache
                    from app.core.utils import normalize_fiscal_year
                    doc_fy = normalize_fiscal_year(doc.fiscal_year) if doc.fiscal_year else None

                    await cache.delete(f"financial_summary:overview:{doc.company_id}")
                    await cache.invalidate_pattern(f"investment_analysis:v1:{doc.company_id}:*")
                    await cache.invalidate_pattern(f"investment_task_active:{doc.company_id}:*")
                    if doc_fy:
                        await cache.delete(f"investment_analysis:v1:{doc.company_id}:{doc_fy}")
                        await cache.delete(f"investment_task_active:{doc.company_id}:{doc_fy}")
                    logger.info(f"Invalidated financial & investment analysis cache for company {doc.company_id} on doc completion (FY={doc_fy}).")
                except Exception as cache_err:
                    logger.warning(f"Failed to clear cache on doc completion for company {doc.company_id}: {cache_err}")

            except ValueError as ve:
                logger.bind(document_id=document_id).error(f"RAG pipeline ingestion failed (Validation): {ve}")
                await db.rollback()
                try:
                    doc = await doc_repo.get(id=document_id)
                    if doc:
                        doc.processing_status = ProcessingStatus.failed
                        await doc_repo.update(db_obj=doc, obj_in={})
                        await db.commit()
                except Exception as status_err:
                    logger.error(f"Failed to update document status to failed: {status_err}")
                raise ve
            except Exception as e:
                logger.bind(document_id=document_id).error(f"RAG pipeline ingestion failed (Execution error): {e}")
                await db.rollback()
                try:
                    doc = await doc_repo.get(id=document_id)
                    if doc:
                        doc.processing_status = ProcessingStatus.failed
                        await doc_repo.update(db_obj=doc, obj_in={})
                        await db.commit()
                except Exception as status_err:
                    logger.error(f"Failed to update document status to failed: {status_err}")
                raise e
            finally:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except Exception as cleanup_err:
                        logger.warning(f"Failed to unlink temp file '{temp_path}': {cleanup_err}")
    finally:
        await local_engine.dispose()


@celery_app.task(name="app.services.tasks.process_news")
def process_news_task(news_payload: dict):
    logger.info("Background news processing task triggered.")
    try:
        asyncio.run(process_news(news_payload))
    except Exception as exc:
        logger.error(f"Fatal error in process_news_task: {exc}")
        raise exc


async def process_news(news_payload: dict):
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

            req = NewsIngestionRequest(**news_payload)
            ingested = await news_service.ingest_news(req)
            logger.info(f"Asynchronously ingested {len(ingested)} news articles.")

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
            self.update_state(state="PROGRESS", meta={"message": "Calculating DCF valuation and WACC..."})
            valuation_service = ValuationService(db)
            valuation = await valuation_service.calculate_valuation(
                company_id=co_uuid,
                fiscal_year=fiscal_year
            )

            self.update_state(state="PROGRESS", meta={"message": "Retrieving company filing contexts..."})
            report_service = ResearchReportService(db)

            self.update_state(state="PROGRESS", meta={"message": "Generating institutional research report..."})
            report_markdown = await report_service.generate_report(
                company_id=co_uuid,
                fiscal_year=fiscal_year
            )

            company_name = report_markdown.split("\n")[0].replace("# INVESTMENT RESEARCH REPORT:", "").strip()
            valuation_dict = valuation.model_dump()

            result_payload = {
                "company_id": company_id,
                "company_name": company_name,
                "valuation_summary": valuation_dict,
                "intrinsic_value": valuation.dcf_details.intrinsic_share_price,
                "sensitivity_analysis": valuation_dict["sensitivity_grid"],
                "research_report": report_markdown
            }

            from app.core.cache import cache
            from app.core.utils import normalize_fiscal_year
            canonical_fy = normalize_fiscal_year(fiscal_year)
            await cache.set(f"investment_analysis:v1:{company_id}:{canonical_fy}", result_payload, ttl=1800)
            await cache.delete(f"investment_task_active:{company_id}:{canonical_fy}")

            return result_payload
    finally:
        await local_engine.dispose()


@celery_app.task(name="app.services.tasks.sweep_pending_documents")
def sweep_pending_documents_task():
    """
    Periodic Celery Beat sweeper task.
    Finds documents with processing_status = 'pending' created more than 10 minutes ago
    and auto-triggers process_document_task for each stuck document.
    """
    logger.info("Celery Beat Sweeper: Checking for stuck 'pending' documents...")
    asyncio.run(_sweep_pending_documents_async())


async def _sweep_pending_documents_async(threshold_minutes: int = 10):
    """
    Creates its own engine per invocation to avoid the asyncpg "Future attached
    to a different loop" crash that occurs when reusing the module-level
    SessionLocal across multiple asyncio.run() calls (each creates a new loop).
    """
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.core.config import settings
    from app.models.document import Document, ProcessingStatus

    local_engine = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URI,
        echo=False,
        future=True,
    )
    LocalSession = async_sessionmaker(
        bind=local_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=threshold_minutes)
        async with LocalSession() as db:
            stmt = select(Document).where(
                Document.processing_status == ProcessingStatus.pending,
                Document.created_at <= cutoff,
            )
            res = await db.execute(stmt)
            stuck_docs = res.scalars().all()

        if not stuck_docs:
            logger.info("Celery Beat Sweeper: No stuck pending documents found.")
            return

        logger.warning(f"Celery Beat Sweeper: Found {len(stuck_docs)} stuck pending documents. Enqueuing tasks...")
        for doc in stuck_docs:
            logger.info(f"Celery Beat Sweeper: Auto-triggering process_document_task for doc {doc.id} ('{doc.file_name}')")
            process_document_task.delay(str(doc.id))
    finally:
        await local_engine.dispose()

