"""Add dedicated columns to document_chunks

Revision ID: f4c91ecad923
Revises: f94eb9d91429
Create Date: 2026-07-03 11:32:47.764759

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4c91ecad923'
down_revision: Union[str, None] = 'f94eb9d91429'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new columns to document_chunks table
    op.add_column('document_chunks', sa.Column('company_id', sa.UUID(), nullable=True))
    op.add_column('document_chunks', sa.Column('page_number', sa.Integer(), nullable=True))
    op.add_column('document_chunks', sa.Column('chunk_index', sa.Integer(), nullable=True))
    op.add_column(
        'document_chunks',
        sa.Column(
            'document_type',
            sa.Enum('annual_report', 'quarterly_report', 'investor_presentation', 'earnings_call', 'other', name='documenttype'),
            nullable=True
        )
    )
    op.add_column('document_chunks', sa.Column('fiscal_year', sa.Integer(), nullable=True))
    op.add_column('document_chunks', sa.Column('section_title', sa.String(length=255), nullable=True))

    # 2. Make metadata_json column nullable (it was not nullable originally in previous migration)
    op.alter_column('document_chunks', 'metadata_json', existing_type=sa.JSON(), nullable=True)

    # 3. Create foreign key constraint
    op.create_foreign_key(
        'fk_document_chunks_company_id_companies',
        'document_chunks', 'companies',
        ['company_id'], ['id'],
        ondelete='CASCADE'
    )

    # 4. Create indexes
    op.create_index('ix_document_chunks_company_id', 'document_chunks', ['company_id'], unique=False)
    op.create_index('ix_document_chunks_document_type', 'document_chunks', ['document_type'], unique=False)

    # 5. For existing rows (if any), set columns to not nullable after filling data,
    # but since this is a fresh setup or active dev environment, we make them nullable first,
    # then alter to nullable=False to satisfy constraints.
    op.alter_column('document_chunks', 'company_id', nullable=False)
    op.alter_column('document_chunks', 'page_number', nullable=False)
    op.alter_column('document_chunks', 'chunk_index', nullable=False)
    op.alter_column('document_chunks', 'document_type', nullable=False)
    op.alter_column('document_chunks', 'fiscal_year', nullable=False)


def downgrade() -> None:
    # Drop indexes and foreign keys
    op.drop_index('ix_document_chunks_document_type', table_name='document_chunks')
    op.drop_index('ix_document_chunks_company_id', table_name='document_chunks')
    op.drop_constraint('fk_document_chunks_company_id_companies', 'document_chunks', type_='foreignkey')

    # Re-make metadata_json not nullable
    op.alter_column('document_chunks', 'metadata_json', existing_type=sa.JSON(), nullable=False)

    # Drop columns
    op.drop_column('document_chunks', 'section_title')
    op.drop_column('document_chunks', 'fiscal_year')
    op.drop_column('document_chunks', 'document_type')
    op.drop_column('document_chunks', 'chunk_index')
    op.drop_column('document_chunks', 'page_number')
    op.drop_column('document_chunks', 'company_id')
