"""Add document table

Revision ID: 19ef8e52b313
Revises: dcb6d55aaeba
Create Date: 2026-07-03 10:59:13.698837

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '19ef8e52b313'
down_revision: Union[str, None] = 'dcb6d55aaeba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create documents table
    op.create_table(
        'documents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column(
            'document_type',
            sa.Enum('annual_report', 'quarterly_report', 'investor_presentation', 'earnings_call', 'other', name='documenttype'),
            nullable=False
        ),
        sa.Column('fiscal_year', sa.Integer(), nullable=False),
        sa.Column('quarter', sa.Integer(), nullable=True),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=512), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=False),
        sa.Column(
            'upload_status',
            sa.Enum('pending', 'completed', 'failed', name='uploadstatus'),
            nullable=False
        ),
        sa.Column(
            'processing_status',
            sa.Enum('pending', 'processing', 'completed', 'failed', name='processingstatus'),
            nullable=False
        ),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. Create indexes
    op.create_index('ix_documents_company_id', 'documents', ['company_id'], unique=False)
    op.create_index('ix_documents_document_type', 'documents', ['document_type'], unique=False)
    op.create_index('ix_documents_id', 'documents', ['id'], unique=False)


def downgrade() -> None:
    # Drop indexes and table with try-catch blocks for safety
    try:
        op.drop_index('ix_documents_id', table_name='documents')
    except Exception:
        pass
    try:
        op.drop_index('ix_documents_document_type', table_name='documents')
    except Exception:
        pass
    try:
        op.drop_index('ix_documents_company_id', table_name='documents')
    except Exception:
        pass
    try:
        op.drop_table('documents')
    except Exception:
        pass

    # Drop enums
    try:
        sa.Enum(name='documenttype').drop(op.get_bind(), checkfirst=True)
    except Exception:
        pass
    try:
        sa.Enum(name='uploadstatus').drop(op.get_bind(), checkfirst=True)
    except Exception:
        pass
    try:
        sa.Enum(name='processingstatus').drop(op.get_bind(), checkfirst=True)
    except Exception:
        pass
