"""add_nickname_fields_to_speaker_mapping

Revision ID: add_nickname_fields
Revises: 6ca705415bbd
Create Date: 2025-11-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = 'add_nickname_fields'
down_revision: Union[str, None] = '6ca705415bbd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nickname and nickname_metadata columns to speaker_mappings table
    op.add_column('speaker_mappings', sa.Column('nickname', sa.String(length=100), nullable=True))
    op.add_column('speaker_mappings', sa.Column('nickname_metadata', mysql.JSON(), nullable=True))


def downgrade() -> None:
    # Remove nickname and nickname_metadata columns from speaker_mappings table
    op.drop_column('speaker_mappings', 'nickname_metadata')
    op.drop_column('speaker_mappings', 'nickname')

