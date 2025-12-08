from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class UserConfirmation(Base):
    """사용자 확정 정보 모델 - 화자 수 및 이름 확정"""
    __tablename__ = "user_confirmations"

    id = Column(Integer, primary_key=True, index=True)
    audio_file_id = Column(Integer, ForeignKey("audio_files.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # 사용자가 확정한 정보
    confirmed_speaker_count = Column(Integer, nullable=False)  # 사용자가 확정한 화자 수
    confirmed_names = Column(JSON, nullable=False)  # 사용자가 확정한 이름 리스트 ["민서", "재형", ...]
    confirmed_nicknames = Column(JSON, nullable=True)  # 사용자가 확정한 닉네임 리스트 ["진행 담당자", "기술 전문가", ...]

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    audio_file = relationship("AudioFile", back_populates="user_confirmation")

    def __repr__(self):
        return f"<UserConfirmation(audio_file_id={self.audio_file_id}, speaker_count={self.confirmed_speaker_count})>"
