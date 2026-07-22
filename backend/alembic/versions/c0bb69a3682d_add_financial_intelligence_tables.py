"""add_financial_intelligence_tables

Revision ID: c0bb69a3682d
Revises: 31701ca6f22d
Create Date: 2026-07-03 13:58:40.976702

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c0bb69a3682d'
down_revision: Union[str, None] = '31701ca6f22d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── financial_periods ──────────────────────────────────────────────────────
    op.create_table(
        'financial_periods',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('fiscal_year', sa.Integer(), nullable=False),
        sa.Column('period_type', sa.Enum(
            'annual', 'q1', 'q2', 'q3', 'q4', name='periodtype'
        ), nullable=False),
        sa.Column('currency', sa.String(10), nullable=False, server_default='USD'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_financial_periods_id', 'financial_periods', ['id'], unique=False)
    op.create_index('ix_financial_periods_company_id', 'financial_periods', ['company_id'], unique=False)
    op.create_index('ix_financial_periods_fiscal_year', 'financial_periods', ['fiscal_year'], unique=False)

    # ── financial_statements ──────────────────────────────────────────────────
    op.create_table(
        'financial_statements',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('period_id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('revenue', sa.Numeric(20, 4), nullable=True),
        sa.Column('ebitda', sa.Numeric(20, 4), nullable=True),
        sa.Column('operating_income', sa.Numeric(20, 4), nullable=True),
        sa.Column('net_profit', sa.Numeric(20, 4), nullable=True),
        sa.Column('eps', sa.Numeric(10, 4), nullable=True),
        sa.Column('total_assets', sa.Numeric(20, 4), nullable=True),
        sa.Column('total_liabilities', sa.Numeric(20, 4), nullable=True),
        sa.Column('shareholders_equity', sa.Numeric(20, 4), nullable=True),
        sa.Column('operating_cash_flow', sa.Numeric(20, 4), nullable=True),
        sa.Column('free_cash_flow', sa.Numeric(20, 4), nullable=True),
        sa.Column('capex', sa.Numeric(20, 4), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['period_id'], ['financial_periods.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_financial_statements_id', 'financial_statements', ['id'], unique=False)
    op.create_index('ix_financial_statements_period_id', 'financial_statements', ['period_id'], unique=False)
    op.create_index('ix_financial_statements_company_id', 'financial_statements', ['company_id'], unique=False)

    # ── financial_evidence ─────────────────────────────────────────────────────
    op.create_table(
        'financial_evidence',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('statement_id', sa.UUID(), nullable=False),
        sa.Column('financial_field', sa.String(100), nullable=False),
        sa.Column('extracted_value', sa.Numeric(20, 4), nullable=True),
        sa.Column('document_title', sa.String(500), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=False),
        sa.Column('section_title', sa.String(500), nullable=True),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('similarity_score', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['statement_id'], ['financial_statements.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_financial_evidence_id', 'financial_evidence', ['id'], unique=False)
    op.create_index('ix_financial_evidence_statement_id', 'financial_evidence', ['statement_id'], unique=False)
    op.create_index('ix_financial_evidence_financial_field', 'financial_evidence', ['financial_field'], unique=False)

    # ── financial_metrics ──────────────────────────────────────────────────────
    op.create_table(
        'financial_metrics',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('statement_id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('revenue_growth_yoy', sa.Numeric(10, 4), nullable=True),
        sa.Column('ebitda_margin', sa.Numeric(10, 4), nullable=True),
        sa.Column('net_profit_margin', sa.Numeric(10, 4), nullable=True),
        sa.Column('roe', sa.Numeric(10, 4), nullable=True),
        sa.Column('roce', sa.Numeric(10, 4), nullable=True),
        sa.Column('debt_to_equity', sa.Numeric(10, 4), nullable=True),
        sa.Column('current_ratio', sa.Numeric(10, 4), nullable=True),
        sa.Column('free_cash_flow_yield', sa.Numeric(10, 4), nullable=True),
        sa.Column('eps_growth', sa.Numeric(10, 4), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['statement_id'], ['financial_statements.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_financial_metrics_id', 'financial_metrics', ['id'], unique=False)
    op.create_index('ix_financial_metrics_statement_id', 'financial_metrics', ['statement_id'], unique=False)
    op.create_index('ix_financial_metrics_company_id', 'financial_metrics', ['company_id'], unique=False)

    # ── financial_metric_provenance ────────────────────────────────────────────
    op.create_table(
        'financial_metric_provenance',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('metric_id', sa.UUID(), nullable=False),
        sa.Column('metric_name', sa.String(100), nullable=False),
        sa.Column('formula', sa.String(500), nullable=False),
        sa.Column('input_fields', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['metric_id'], ['financial_metrics.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_financial_metric_provenance_id', 'financial_metric_provenance', ['id'], unique=False)
    op.create_index('ix_financial_metric_provenance_metric_id', 'financial_metric_provenance', ['metric_id'], unique=False)
    op.create_index('ix_financial_metric_provenance_metric_name', 'financial_metric_provenance', ['metric_name'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_financial_metric_provenance_metric_name', table_name='financial_metric_provenance')
    op.drop_index('ix_financial_metric_provenance_metric_id', table_name='financial_metric_provenance')
    op.drop_index('ix_financial_metric_provenance_id', table_name='financial_metric_provenance')
    op.drop_table('financial_metric_provenance')

    op.drop_index('ix_financial_metrics_company_id', table_name='financial_metrics')
    op.drop_index('ix_financial_metrics_statement_id', table_name='financial_metrics')
    op.drop_index('ix_financial_metrics_id', table_name='financial_metrics')
    op.drop_table('financial_metrics')

    op.drop_index('ix_financial_evidence_financial_field', table_name='financial_evidence')
    op.drop_index('ix_financial_evidence_statement_id', table_name='financial_evidence')
    op.drop_index('ix_financial_evidence_id', table_name='financial_evidence')
    op.drop_table('financial_evidence')

    op.drop_index('ix_financial_statements_company_id', table_name='financial_statements')
    op.drop_index('ix_financial_statements_period_id', table_name='financial_statements')
    op.drop_index('ix_financial_statements_id', table_name='financial_statements')
    op.drop_table('financial_statements')

    op.drop_index('ix_financial_periods_fiscal_year', table_name='financial_periods')
    op.drop_index('ix_financial_periods_company_id', table_name='financial_periods')
    op.drop_index('ix_financial_periods_id', table_name='financial_periods')
    op.drop_table('financial_periods')

    op.execute("DROP TYPE IF EXISTS periodtype")

