"""
Speaker Profile Model
동일 화자를 여러 파일에서 자동 인식하기 위한 프로필
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class SpeakerProfile(Base):
    """화자 프로필 모델"""
    __tablename__ = "speaker_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    speaker_name = Column(String(100), nullable=False)  # 화자 실명 (예: "김민서")

    # 음성 임베딩 (평균 벡터)
    voice_embedding = Column(JSON, nullable=True)  # [0.12, -0.45, ...] (192차원 Senko 임베딩)

    # 텍스트 임베딩 (발화 스타일)
    text_embedding = Column(JSON, nullable=True)  # [0.11, -0.44, ...] (OpenAI text-embedding-3-small)

    # 대표 발화 샘플 (텍스트 유사도 비교용)
    sample_texts = Column(JSON, nullable=True)  # ["안녕하세요", "네, 알겠습니다", ...]

    # 메타데이터
    source_audio_file_id = Column(Integer, ForeignKey("audio_files.id", ondelete="SET NULL"), nullable=True)
    confidence_score = Column(Integer, default=1, nullable=False)  # 프로필 사용 횟수 (높을수록 신뢰도 높음)

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    source_audio_file = relationship("AudioFile", foreign_keys=[source_audio_file_id])

    def __repr__(self):
        return f"<SpeakerProfile(id={self.id}, speaker_name={self.speaker_name}, user_id={self.user_id})>"
