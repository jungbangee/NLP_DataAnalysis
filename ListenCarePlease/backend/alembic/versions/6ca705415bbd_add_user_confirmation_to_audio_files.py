"""add_user_confirmation_to_audio_files

Revision ID: 6ca705415bbd
Revises: 43cddc5d14ed
Create Date: 2025-11-18 12:55:51.364056

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = '6ca705415bbd'
down_revision: Union[str, None] = '43cddc5d14ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create user_confirmations table
    op.create_table(
        'user_confirmations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('audio_file_id', sa.Integer(), nullable=False),
        sa.Column('confirmed_speaker_count', sa.Integer(), nullable=False),
        sa.Column('confirmed_names', mysql.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['audio_file_id'], ['audio_files.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('audio_file_id')
    )
    op.create_index(op.f('ix_user_confirmations_id'), 'user_confirmations', ['id'], unique=False)
    op.create_index(op.f('ix_user_confirmations_audio_file_id'), 'user_confirmations', ['audio_file_id'], unique=False)


def downgrade() -> None:
    # Drop user_confirmations table
    op.drop_index(op.f('ix_user_confirmations_audio_file_id'), table_name='user_confirmations')
    op.drop_index(op.f('ix_user_confirmations_id'), table_name='user_confirmations')
    op.drop_table('user_confirmations')
