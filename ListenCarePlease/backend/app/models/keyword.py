from sqlalchemy import Column, Integer, String, Text, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship
from app.db.base import Base

class KeyTerm(Base):
    """핵심 용어 및 교정 정보 모델"""
    __tablename__ = "key_terms"

    id = Column(Integer, primary_key=True, index=True)
    audio_file_id = Column(Integer, ForeignKey("audio_files.id", ondelete="CASCADE"), nullable=False, index=True)

    # 용어 정보
    term = Column(String(255), nullable=False) # clean_word (대표 용어)
    meaning = Column(Text, nullable=True) # mean (설명)
    glossary_display = Column(String(255), nullable=True) # 해설집용 표기
    synonyms = Column(JSON, nullable=True) # List[str] (동의어, 오타 포함)
    importance = Column(Float, default=0.0) # 중요도 (1-10)
    
    # 위치 정보
    first_appearance_index = Column(Integer, nullable=True) # 첫 등장 발화 인덱스 (정렬용)
    
    # Relationship
    audio_file = relationship("AudioFile", back_populates="key_terms")

    def __repr__(self):
        return f"<KeyTerm(term='{self.term}', importance={self.importance})>"
