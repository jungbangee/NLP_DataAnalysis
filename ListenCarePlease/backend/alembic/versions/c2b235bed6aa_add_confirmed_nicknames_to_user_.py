"""add_confirmed_nicknames_to_user_confirmation

Revision ID: c2b235bed6aa
Revises: add_nickname_fields
Create Date: 2025-11-20 14:49:02.252826

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = 'c2b235bed6aa'
down_revision: Union[str, None] = 'add_nickname_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add confirmed_nicknames column to user_confirmations table
    op.add_column('user_confirmations', sa.Column('confirmed_nicknames', mysql.JSON(), nullable=True))


def downgrade() -> None:
    # Remove confirmed_nicknames column from user_confirmations table
    op.drop_column('user_confirmations', 'confirmed_nicknames')
