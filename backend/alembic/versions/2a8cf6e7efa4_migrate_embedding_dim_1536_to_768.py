"""migrate_embedding_dim_1536_to_768

Revision ID: 2a8cf6e7efa4
Revises: 247da76daefe
Create Date: 2026-07-14 09:57:04.541954

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a8cf6e7efa4'
down_revision: Union[str, None] = '247da76daefe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Purge stale Gemini chunks first
    op.execute("DELETE FROM document_chunks;")
    
    # 2. Alter the embedding column type to vector(768)
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(768);")
    
    # 3. Reset all document statuses to failed
    op.execute("UPDATE documents SET processing_status = 'failed';")



def downgrade() -> None:
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1536);")

