"""add is_active column to documents table

Revision ID: 8b9c0d1e2f3a
Revises: 7a8b9c0d1e2f
Create Date: 2026-08-05 14:35:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '8b9c0d1e2f3a'
down_revision = '7a8b9c0d1e2f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'documents',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true'))
    )
    op.execute("UPDATE documents SET is_active = true WHERE is_active IS NULL;")


def downgrade():
    op.drop_column('documents', 'is_active')
