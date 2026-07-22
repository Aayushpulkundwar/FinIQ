"""add_event_intelligence_tables

Revision ID: 31701ca6f22d
Revises: f4c91ecad923
Create Date: 2026-07-03 12:20:11.289313

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '31701ca6f22d'
down_revision: Union[str, None] = 'f4c91ecad923'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create industries table
    op.create_table(
        'industries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_industries_id', 'industries', ['id'], unique=False)
    op.create_index('ix_industries_name', 'industries', ['name'], unique=True)

    # Create events table
    op.create_table(
        'events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('event_type', sa.Enum(
            'macroeconomic', 'policy', 'regulatory', 'geopolitical', 'industry', 'company_specific',
            name='eventtype'
        ), nullable=False),
        sa.Column('severity', sa.Enum(
            'LOW', 'MEDIUM', 'HIGH', 'CRITICAL',
            name='eventseverity'
        ), nullable=False),
        sa.Column('event_date', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_events_id', 'events', ['id'], unique=False)
    op.create_index('ix_events_event_type', 'events', ['event_type'], unique=False)
    op.create_index('ix_events_severity', 'events', ['severity'], unique=False)

    # Create event_industries association table
    op.create_table(
        'event_industries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('event_id', sa.UUID(), nullable=False),
        sa.Column('industry_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['industry_id'], ['industries.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_event_industries_id', 'event_industries', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_event_industries_id', table_name='event_industries')
    op.drop_table('event_industries')
    op.drop_index('ix_events_severity', table_name='events')
    op.drop_index('ix_events_event_type', table_name='events')
    op.drop_index('ix_events_id', table_name='events')
    op.drop_table('events')
    op.drop_index('ix_industries_name', table_name='industries')
    op.drop_index('ix_industries_id', table_name='industries')
    op.drop_table('industries')
    op.execute("DROP TYPE IF EXISTS eventtype")
    op.execute("DROP TYPE IF EXISTS eventseverity")

