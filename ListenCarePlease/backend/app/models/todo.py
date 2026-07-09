"""
TODO 데이터베이스 모델
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship
from app.db.base import Base
import enum

class TodoPriority(str, enum.Enum):
    """TODO 우선순위"""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

class TodoItem(Base):
    """TODO 아이템 모델"""
    __tablename__ = "todo_items"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("audio_files.id", ondelete="CASCADE"), nullable=False)
    task = Column(Text, nullable=False)  # 할 일 내용
    assignee = Column(String(100), nullable=True)  # 담당자
    due_date = Column(DateTime, nullable=True)  # 마감일 (YYYY-MM-DD HH:MM)
    priority = Column(Enum(TodoPriority), default=TodoPriority.MEDIUM)  # 우선순위
    created_at = Column(DateTime, nullable=False)  # 생성일

    # Relationship
    audio_file = relationship("AudioFile", back_populates="todos")
