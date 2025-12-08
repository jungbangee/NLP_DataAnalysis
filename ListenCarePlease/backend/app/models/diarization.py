from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class DiarizationResult(Base):
    """화자 분리 결과 모델 (I,O.md Step 4)"""
    __tablename__ = "diarization_results"

    id = Column(Integer, primary_key=True, index=True)
    audio_file_id = Column(Integer, ForeignKey("audio_files.id", ondelete="CASCADE"), nullable=False, index=True)

    # 화자 정보
    speaker_label = Column(String(50), nullable=False)  # SPEAKER_00, SPEAKER_01, ...

    # 타임스탬프
    start_time = Column(Float, nullable=False)  # 시작 시간 (초)
    end_time = Column(Float, nullable=False)  # 종료 시간 (초)

    # 음성 임베딩 벡터
    embedding = Column(JSON, nullable=True)  # 임베딩 벡터 배열 [0.12, -0.45, ...]

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    audio_file = relationship("AudioFile", back_populates="diarization_results")

    # 복합 인덱스
    __table_args__ = (
        Index('ix_diar_audio_speaker', 'audio_file_id', 'speaker_label'),
    )

    def __repr__(self):
        return f"<DiarizationResult(id={self.id}, speaker={self.speaker_label}, time={self.start_time}-{self.end_time})>"
