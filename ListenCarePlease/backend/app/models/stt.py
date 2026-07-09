from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class STTResult(Base):
    """STT 결과 모델 (I,O.md Step 3)"""
    __tablename__ = "stt_results"

    id = Column(Integer, primary_key=True, index=True)
    audio_file_id = Column(Integer, ForeignKey("audio_files.id", ondelete="CASCADE"), nullable=False, index=True)

    # 단어 정보
    word_index = Column(Integer, nullable=False)  # 단어 순서
    text = Column(String(100), nullable=False)  # 단어/텍스트

    # 타임스탬프
    start_time = Column(Float, nullable=False)  # 시작 시간 (초)
    end_time = Column(Float, nullable=False)  # 종료 시간 (초)

    # 신뢰도
    confidence = Column(Float, nullable=True)  # 0.0 ~ 1.0

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    audio_file = relationship("AudioFile", back_populates="stt_results")

    # 복합 인덱스
    __table_args__ = (
        Index('ix_stt_audio_word', 'audio_file_id', 'word_index'),
    )

    def __repr__(self):
        return f"<STTResult(id={self.id}, text='{self.text}', time={self.start_time}-{self.end_time})>"
