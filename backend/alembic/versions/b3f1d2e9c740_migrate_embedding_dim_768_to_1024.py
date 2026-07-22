"""migrate_embedding_dim_768_to_1024

Migrates the document_chunks.embedding column from vector(768) (Nomic/nomic-embed-text)
to vector(1024) (BGE-M3/bge-m3 via Ollama).

WHY EMBEDDINGS ARE NULLED OUT:
    Nomic (768-dim) and BGE-M3 (1024-dim) vectors exist in completely different
    semantic vector spaces.  Leaving old Nomic vectors in the column and indexing
    them alongside new BGE-M3 vectors would produce silently incorrect cosine-
    similarity results — nearest-neighbour search would compare incompatible
    number representations.

    All existing rows are therefore deleted before the column type change.
    After this migration you MUST re-ingest all documents so that fresh BGE-M3
    embeddings are generated and stored.

RE-EMBEDDING STEPS (after running this migration):
    1. Ensure `ollama pull bge-m3` has completed on all Ollama hosts.
    2. Re-trigger ingestion for every document via the Celery task:
           from app.services.tasks import process_document
           process_document.delay(str(document_id))
       OR run the one-off re-embedding script if available.
    3. Confirm `document_chunks` rows are repopulated with 1024-dim vectors.

Revision ID: b3f1d2e9c740
Revises: 2a8cf6e7efa4
Create Date: 2026-07-17 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f1d2e9c740'
down_revision: Union[str, None] = '2a8cf6e7efa4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # WARNING: This step permanently removes all stored embeddings.
    # Nomic (768-dim) embeddings are INCOMPATIBLE with BGE-M3 (1024-dim) and
    # cannot be reused.  All documents must be re-ingested after this migration.
    # -------------------------------------------------------------------------

    # 1. Delete all existing document chunks — Nomic vectors cannot be reused
    #    with BGE-M3's vector space.
    print(
        "\n[MIGRATION WARNING] Deleting all document_chunks rows.\n"
        "  Reason: Nomic (768-dim) embeddings are incompatible with BGE-M3 (1024-dim).\n"
        "  Action required: Re-ingest all documents after this migration completes.\n"
    )
    op.execute("DELETE FROM document_chunks;")

    # 2. Alter the embedding column type from vector(768) → vector(1024)
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1024);")

    # 3. Reset all document processing statuses to 'failed' so re-ingestion
    #    can be triggered cleanly via the normal pipeline.
    op.execute("UPDATE documents SET processing_status = 'failed';")


def downgrade() -> None:
    # Reverse: delete BGE-M3 chunks and revert column to vector(768).
    # Note: you will need to re-ingest documents with Nomic to restore data.
    op.execute("DELETE FROM document_chunks;")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(768);")
    op.execute("UPDATE documents SET processing_status = 'failed';")
