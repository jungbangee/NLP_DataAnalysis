from sqlalchemy import Column, Integer, String, Text, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base

class MeetingSection(Base):
    """회의 구간 분석 결과 모델"""
    __tablename__ = "meeting_sections"

    id = Column(Integer, primary_key=True, index=True)
    audio_file_id = Column(Integer, ForeignKey("audio_files.id", ondelete="CASCADE"), nullable=False, index=True)

    # 구간 정보
    section_index = Column(Integer, nullable=False) # 섹션 순서
    section_title = Column(String(255), nullable=True) # 섹션 제목
    start_index = Column(Integer, nullable=False) # 시작 발화 인덱스
    end_index = Column(Integer, nullable=False) # 종료 발화 인덱스
    
    # 분석 내용
    meeting_type = Column(String(50), nullable=True)
    discussion_summary = Column(Text, nullable=True)
    decisions = Column(JSON, nullable=True) # List[str]
    action_items = Column(JSON, nullable=True) # List[Dict]
    
    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    audio_file = relationship("AudioFile", back_populates="meeting_sections")

    def __repr__(self):
        return f"<MeetingSection(id={self.id}, title='{self.section_title}', range={self.start_index}-{self.end_index})>"
