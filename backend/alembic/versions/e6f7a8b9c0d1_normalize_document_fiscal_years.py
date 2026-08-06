"""normalize fiscal year for verified existing documents

Revision ID: e6f7a8b9c0d1
Revises: b3f1d2e9c740
Create Date: 2026-08-05 12:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e6f7a8b9c0d1'
down_revision = '62063797a222'
branch_labels = None
depends_on = None

# ID-scoped list of exact verified documents to normalize
VERIFIED_DOC_IDS = (
    "'462cc31b-37ee-404d-947c-9d01c1788a61'",  # Bharti Airtel
    "'96782ade-967e-4c07-8cfd-31f5db914667'",  # Arvind Limited
    "'83a718c5-ae80-491a-9ea8-aa245bc96fae'",  # TVS Supply Chain
    "'a0dce91c-3990-41c9-80bc-28b93d2d1a9e'",  # VRL Logistics
)


def upgrade():
    ids_str = ", ".join(VERIFIED_DOC_IDS)
    
    # 1. Update documents table for exact verified IDs only
    op.execute(f"UPDATE documents SET fiscal_year = 2026 WHERE id IN ({ids_str});")
    
    # 2. Update document_chunks table for exact verified document IDs only
    op.execute(f"UPDATE document_chunks SET fiscal_year = 2026 WHERE document_id IN ({ids_str});")


def downgrade():
    pass
