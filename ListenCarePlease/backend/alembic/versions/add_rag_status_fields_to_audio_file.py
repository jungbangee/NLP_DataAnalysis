"""add_rag_status_fields_to_audio_file

Revision ID: add_rag_status_fields
Revises: c2b235bed6aa
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_rag_status_fields'
down_revision: Union[str, None] = '11cfae3aff65'  # Add processing status fields 이후
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # RAG 벡터 DB 상태 컬럼 추가
    op.add_column('audio_files', sa.Column('rag_collection_name', sa.String(length=100), nullable=True))
    op.add_column('audio_files', sa.Column('rag_initialized', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('audio_files', sa.Column('rag_initialized_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # 컬럼 제거
    op.drop_column('audio_files', 'rag_initialized_at')
    op.drop_column('audio_files', 'rag_initialized')
    op.drop_column('audio_files', 'rag_collection_name')

