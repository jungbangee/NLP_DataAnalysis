from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class PreprocessingResult(Base):
    """전처리 결과 모델 (I,O.md Step 2)"""
    __tablename__ = "preprocessing_results"

    id = Column(Integer, primary_key=True, index=True)
    audio_file_id = Column(Integer, ForeignKey("audio_files.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # 전처리된 파일 경로
    stt_input_path = Column(String(500), nullable=False)  # VAD만 적용 (STT용)
    diar_input_path = Column(String(500), nullable=False)  # VAD + 노이즈 제거 (Diarization용)

    # 메타데이터
    processing_time = Column(Float, nullable=True)  # 처리 시간 (초)

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    audio_file = relationship("AudioFile", back_populates="preprocessing_result")

    def __repr__(self):
        return f"<PreprocessingResult(id={self.id}, audio_file_id={self.audio_file_id})>"
