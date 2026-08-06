"""add heartbeat_at column to documents table

Revision ID: 7a8b9c0d1e2f
Revises: e6f7a8b9c0d1
Create Date: 2026-08-05 13:15:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '7a8b9c0d1e2f'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('heartbeat_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('documents', 'heartbeat_at')
