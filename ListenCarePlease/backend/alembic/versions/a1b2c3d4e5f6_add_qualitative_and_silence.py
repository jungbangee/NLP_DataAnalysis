"""Add qualitative and silence analysis columns

Revision ID: a1b2c3d4e5f6
Revises: 89466e87344b
Create Date: 2025-12-01 15:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '2eddc0de3d29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Get existing columns
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [c['name'] for c in inspector.get_columns('meeting_efficiency_analysis')]

    if 'qualitative_analysis' not in columns:
        op.add_column('meeting_efficiency_analysis',
                      sa.Column('qualitative_analysis', sa.Text(), nullable=True))

    if 'silence_analysis' not in columns:
        op.add_column('meeting_efficiency_analysis',
                      sa.Column('silence_analysis', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('meeting_efficiency_analysis', 'silence_analysis')
    op.drop_column('meeting_efficiency_analysis', 'qualitative_analysis')
