"""Add interaction_analysis column

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2025-12-02 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5f6g7h8i9j0'
down_revision: Union[str, None] = 'd4e5f6g7h8i9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if column exists first to be safe
    conn = op.get_bind()
    from sqlalchemy.engine.reflection import Inspector
    inspector = Inspector.from_engine(conn)
    columns = [c['name'] for c in inspector.get_columns('meeting_efficiency_analysis')]

    if 'interaction_analysis' not in columns:
        op.add_column('meeting_efficiency_analysis',
                      sa.Column('interaction_analysis', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('meeting_efficiency_analysis', 'interaction_analysis')
