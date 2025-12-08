"""Add missing tables (key_terms, meeting_sections, todo_items)

Revision ID: d4e5f6g7h8i9
Revises: a1b2c3d4e5f6
Create Date: 2025-12-01 17:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6g7h8i9'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create key_terms table
    op.create_table('key_terms',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('audio_file_id', sa.Integer(), nullable=False),
        sa.Column('term', sa.String(length=255), nullable=False),
        sa.Column('meaning', sa.Text(), nullable=True),
        sa.Column('glossary_display', sa.String(length=255), nullable=True),
        sa.Column('synonyms', sa.JSON(), nullable=True),
        sa.Column('importance', sa.Float(), nullable=True),
        sa.Column('first_appearance_index', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['audio_file_id'], ['audio_files.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_key_terms_audio_file_id'), 'key_terms', ['audio_file_id'], unique=False)
    op.create_index(op.f('ix_key_terms_id'), 'key_terms', ['id'], unique=False)

    # 2. Create meeting_sections table
    op.create_table('meeting_sections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('audio_file_id', sa.Integer(), nullable=False),
        sa.Column('section_index', sa.Integer(), nullable=False),
        sa.Column('section_title', sa.String(length=255), nullable=True),
        sa.Column('start_index', sa.Integer(), nullable=False),
        sa.Column('end_index', sa.Integer(), nullable=False),
        sa.Column('meeting_type', sa.String(length=50), nullable=True),
        sa.Column('discussion_summary', sa.Text(), nullable=True),
        sa.Column('decisions', sa.JSON(), nullable=True),
        sa.Column('action_items', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['audio_file_id'], ['audio_files.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_meeting_sections_audio_file_id'), 'meeting_sections', ['audio_file_id'], unique=False)
    op.create_index(op.f('ix_meeting_sections_id'), 'meeting_sections', ['id'], unique=False)

    # 3. Create todo_items table
    op.create_table('todo_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=False),
        sa.Column('task', sa.Text(), nullable=False),
        sa.Column('assignee', sa.String(length=100), nullable=True),
        sa.Column('due_date', sa.DateTime(), nullable=True),
        sa.Column('priority', sa.Enum('HIGH', 'MEDIUM', 'LOW', name='todopriority'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['file_id'], ['audio_files.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_todo_items_id'), 'todo_items', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_todo_items_id'), table_name='todo_items')
    op.drop_table('todo_items')
    
    op.drop_index(op.f('ix_meeting_sections_id'), table_name='meeting_sections')
    op.drop_index(op.f('ix_meeting_sections_audio_file_id'), table_name='meeting_sections')
    op.drop_table('meeting_sections')
    
    op.drop_index(op.f('ix_key_terms_id'), table_name='key_terms')
    op.drop_index(op.f('ix_key_terms_audio_file_id'), table_name='key_terms')
    op.drop_table('key_terms')
