"""Add recent selections and company name index

Revision ID: a225e36f0190
Revises: 037380a770f8
Create Date: 2026-07-12 11:55:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a225e36f0190'
down_revision: Union[str, None] = '037380a770f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create index on companies.company_name
    op.create_index('ix_companies_company_name', 'companies', ['company_name'], unique=False)

    # 2. Create recent_company_selections table
    op.create_table(
        'recent_company_selections',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('selected_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'company_id', name='uq_user_company_selection')
    )

    # 3. Create indexes for recent_company_selections
    op.create_index('ix_recent_company_selections_id', 'recent_company_selections', ['id'], unique=False)
    op.create_index('ix_recent_company_selections_user_id', 'recent_company_selections', ['user_id'], unique=False)
    op.create_index('ix_recent_company_selections_company_id', 'recent_company_selections', ['company_id'], unique=False)


def downgrade() -> None:
    # Drop indexes and table
    op.drop_index('ix_recent_company_selections_company_id', table_name='recent_company_selections')
    op.drop_index('ix_recent_company_selections_user_id', table_name='recent_company_selections')
    op.drop_index('ix_recent_company_selections_id', table_name='recent_company_selections')
    op.drop_table('recent_company_selections')

    # Drop index on companies.company_name
    op.drop_index('ix_companies_company_name', table_name='companies')
