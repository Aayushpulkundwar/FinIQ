"""Add company table

Revision ID: dcb6d55aaeba
Revises: None
Create Date: 2026-07-03 10:35:05.261439

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dcb6d55aaeba'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create companies table
    op.create_table(
        'companies',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_name', sa.String(length=255), nullable=False),
        sa.Column('ticker_symbol', sa.String(length=50), nullable=False),
        sa.Column('exchange', sa.String(length=100), nullable=False),
        sa.Column('sector', sa.String(length=100), nullable=False),
        sa.Column('industry', sa.String(length=100), nullable=False),
        sa.Column('isin', sa.String(length=50), nullable=False),
        sa.Column('website', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('ix_companies_id', 'companies', ['id'], unique=False)
    op.create_index('ix_companies_isin', 'companies', ['isin'], unique=True)
    op.create_index('ix_companies_ticker_symbol', 'companies', ['ticker_symbol'], unique=True)


def downgrade() -> None:
    # Drop indexes and table
    op.drop_index('ix_companies_ticker_symbol', table_name='companies')
    op.drop_index('ix_companies_isin', table_name='companies')
    op.drop_index('ix_companies_id', table_name='companies')
    op.drop_table('companies')
