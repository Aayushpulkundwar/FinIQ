"""add_file_hash_to_documents

Revision ID: 037380a770f8
Revises: e0e7a17df9a2
Create Date: 2026-07-09 12:54:56.178637

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '037380a770f8'
down_revision: Union[str, None] = 'e0e7a17df9a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('documents')]
    if 'file_hash' not in columns:
        op.add_column('documents', sa.Column('file_hash', sa.String(length=64), nullable=True))
        op.create_index(op.f('ix_documents_file_hash'), 'documents', ['file_hash'], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('documents')]
    if 'file_hash' in columns:
        op.drop_index(op.f('ix_documents_file_hash'), table_name='documents')
        op.drop_column('documents', 'file_hash')
