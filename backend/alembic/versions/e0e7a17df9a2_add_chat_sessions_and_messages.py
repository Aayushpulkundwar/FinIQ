"""add_chat_sessions_and_messages

Revision ID: e0e7a17df9a2
Revises: 4202f17892d8
Create Date: 2026-07-09 08:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e0e7a17df9a2'
down_revision: Union[str, None] = '4202f17892d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Define role enum explicitly with create_type=False and check/create first
    role_enum = postgresql.ENUM('user', 'assistant', 'system', name='chatrole', create_type=False)
    role_enum.create(op.get_bind(), checkfirst=True)

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # 1. Create chat_sessions table if not exists
    if 'chat_sessions' not in tables:
        op.create_table(
            'chat_sessions',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('ticker', sa.String(length=50), nullable=True),
            sa.Column('title', sa.String(length=255), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_chat_sessions_id'), 'chat_sessions', ['id'], unique=False)
        op.create_index(op.f('ix_chat_sessions_ticker'), 'chat_sessions', ['ticker'], unique=False)

    # 2. Create chat_messages table if not exists
    if 'chat_messages' not in tables:
        op.create_table(
            'chat_messages',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('session_id', sa.Uuid(), nullable=False),
            sa.Column('role', role_enum, nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_chat_messages_id'), 'chat_messages', ['id'], unique=False)
        op.create_index(op.f('ix_chat_messages_session_id'), 'chat_messages', ['session_id'], unique=False)
        op.create_index('ix_chat_messages_created_at_id', 'chat_messages', ['created_at', 'id'], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'chat_messages' in tables:
        op.drop_index('ix_chat_messages_created_at_id', table_name='chat_messages')
        op.drop_index(op.f('ix_chat_messages_session_id'), table_name='chat_messages')
        op.drop_index(op.f('ix_chat_messages_id'), table_name='chat_messages')
        op.drop_table('chat_messages')

    if 'chat_sessions' in tables:
        op.drop_index(op.f('ix_chat_sessions_ticker'), table_name='chat_sessions')
        op.drop_index(op.f('ix_chat_sessions_id'), table_name='chat_sessions')
        op.drop_table('chat_sessions')
    
    # Drop chatrole enum type if it exists
    role_enum = postgresql.ENUM('user', 'assistant', 'system', name='chatrole', create_type=False)
    role_enum.drop(bind, checkfirst=True)
