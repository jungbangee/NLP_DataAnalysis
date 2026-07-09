from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Enum, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
import enum


class FinalTranscript(Base):
    """최종 대본 모델 (I,O.md Step 5f)"""
    __tablename__ = "final_transcripts"

    id = Column(Integer, primary_key=True, index=True)
    audio_file_id = Column(Integer, ForeignKey("audio_files.id", ondelete="CASCADE"), nullable=False, index=True)

    # 발화 정보
    segment_index = Column(Integer, nullable=False)  # 발화 순서
    speaker_name = Column(String(100), nullable=False)  # 화자 이름 ("김민서", "박철수" 등)

    # 타임스탬프
    start_time = Column(Float, nullable=False)  # 시작 시간 (초)
    end_time = Column(Float, nullable=False)  # 종료 시간 (초)

    # 텍스트
    text = Column(Text, nullable=False)  # 발화 내용

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    audio_file = relationship("AudioFile", back_populates="final_transcripts")

    # 복합 인덱스
    __table_args__ = (
        Index('ix_transcript_audio_segment', 'audio_file_id', 'segment_index'),
    )

    def __repr__(self):
        return f"<FinalTranscript(id={self.id}, speaker='{self.speaker_name}', segment={self.segment_index})>"


class SummaryType(str, enum.Enum):
    """요약 유형"""
    SUMMARY = "summary"  # 텍스트 요약
    SUBTITLE = "subtitle"  # 자막 파일


class Summary(Base):
    """요약 결과 모델 (I,O.md Step 6)"""
    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True, index=True)
    audio_file_id = Column(Integer, ForeignKey("audio_files.id", ondelete="CASCADE"), nullable=False, index=True)

    # 요약 정보
    summary_type = Column(Enum(SummaryType), nullable=False)
    content = Column(Text, nullable=False)  # 요약 내용 또는 자막 파일 경로

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    audio_file = relationship("AudioFile", back_populates="summaries")

    def __repr__(self):
        return f"<Summary(id={self.id}, type={self.summary_type}, audio_file_id={self.audio_file_id})>"
