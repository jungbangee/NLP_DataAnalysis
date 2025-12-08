"""Add insight columns to efficiency analysis

Revision ID: 89466e87344b
Revises: b15f90cfcefa
Create Date: 2025-11-28 00:50:57.692633

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = '89466e87344b'
down_revision: Union[str, None] = 'b15f90cfcefa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Get existing columns
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [c['name'] for c in inspector.get_columns('meeting_efficiency_analysis')]

    # Add insight columns to meeting_efficiency_analysis table
    if 'entropy_insight' not in columns:
        op.add_column('meeting_efficiency_analysis',
                      sa.Column('entropy_insight', sa.String(500), nullable=True))
    if 'overall_ttr_insight' not in columns:
        op.add_column('meeting_efficiency_analysis',
                      sa.Column('overall_ttr_insight', sa.String(500), nullable=True))
    if 'overall_info_insight' not in columns:
        op.add_column('meeting_efficiency_analysis',
                      sa.Column('overall_info_insight', sa.String(500), nullable=True))
    if 'overall_sentence_prob_insight' not in columns:
        op.add_column('meeting_efficiency_analysis',
                      sa.Column('overall_sentence_prob_insight', sa.String(500), nullable=True))
    if 'overall_ppl_insight' not in columns:
        op.add_column('meeting_efficiency_analysis',
                      sa.Column('overall_ppl_insight', sa.String(500), nullable=True))

    # Add overall meeting metrics columns (if not exist)
    if 'overall_ttr' not in columns:
        op.add_column('meeting_efficiency_analysis',
                      sa.Column('overall_ttr', sa.JSON(), nullable=True))
    if 'overall_information_content' not in columns:
        op.add_column('meeting_efficiency_analysis',
                      sa.Column('overall_information_content', sa.JSON(), nullable=True))
    if 'overall_sentence_probability' not in columns:
        op.add_column('meeting_efficiency_analysis',
                      sa.Column('overall_sentence_probability', sa.JSON(), nullable=True))
    if 'overall_perplexity' not in columns:
        op.add_column('meeting_efficiency_analysis',
                      sa.Column('overall_perplexity', sa.JSON(), nullable=True))


def downgrade() -> None:
    # Remove insight columns
    op.drop_column('meeting_efficiency_analysis', 'overall_ppl_insight')
    op.drop_column('meeting_efficiency_analysis', 'overall_sentence_prob_insight')
    op.drop_column('meeting_efficiency_analysis', 'overall_info_insight')
    op.drop_column('meeting_efficiency_analysis', 'overall_ttr_insight')
    op.drop_column('meeting_efficiency_analysis', 'entropy_insight')

    # Note: We don't drop overall metrics columns as they might have been added by another migration
