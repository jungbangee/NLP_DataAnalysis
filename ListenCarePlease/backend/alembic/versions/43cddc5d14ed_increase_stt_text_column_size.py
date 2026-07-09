"""increase_stt_text_column_size

Revision ID: 43cddc5d14ed
Revises: 28142f56d2d2
Create Date: 2025-11-18 07:52:10.739286

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '43cddc5d14ed'
down_revision: Union[str, None] = '28142f56d2d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Change text column from VARCHAR(100) to TEXT to accommodate longer transcription segments
    op.alter_column('stt_results', 'text',
                    existing_type=sa.String(length=100),
                    type_=sa.Text(),
                    existing_nullable=False)


def downgrade() -> None:
    # Revert TEXT back to VARCHAR(100)
    op.alter_column('stt_results', 'text',
                    existing_type=sa.Text(),
                    type_=sa.String(length=100),
                    existing_nullable=False)
