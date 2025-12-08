"""Add google tokens to users

Revision ID: add_google_tokens
Revises: e5f6g7h8i9j0
Create Date: 2025-12-05 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_google_tokens'
down_revision: Union[str, None] = 'e5f6g7h8i9j0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if columns exist first to be safe
    conn = op.get_bind()
    from sqlalchemy.engine.reflection import Inspector
    inspector = Inspector.from_engine(conn)
    columns = [c['name'] for c in inspector.get_columns('users')]

    if 'google_access_token' not in columns:
        op.add_column('users', sa.Column('google_access_token', sa.String(length=255), nullable=True))
    
    if 'google_refresh_token' not in columns:
        op.add_column('users', sa.Column('google_refresh_token', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'google_refresh_token')
    op.drop_column('users', 'google_access_token')
