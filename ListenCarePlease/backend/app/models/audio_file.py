from sqlalchemy import Column, Integer, String, BigInteger, Float, DateTime, Enum, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
import enum


class FileStatus(str, enum.Enum):
    """파일 처리 상태"""
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AudioFile(Base):
    """오디오 파일 모델"""
    __tablename__ = "audio_files"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # 파일 정보
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(BigInteger, nullable=False)  # bytes
    duration = Column(Float, nullable=True)  # seconds
    mimetype = Column(String(50), nullable=False)

    # 상태
    status = Column(Enum(FileStatus), default=FileStatus.UPLOADED, nullable=False, index=True)

    # 처리 진행 상태 (대시보드용)
    processing_step = Column(String(50), nullable=True)  # 'preprocessing', 'stt', 'diarization', 'ner', 'completed'
    processing_progress = Column(Integer, default=0, nullable=False)  # 0-100
    processing_message = Column(String(200), nullable=True)  # "전처리 중...", "STT 진행 중..."
    error_message = Column(Text, nullable=True)  # 에러 발생 시 메시지

    # RAG 벡터 DB 상태
    rag_collection_name = Column(String(100), nullable=True)  # ChromaDB 컬렉션 이름 (예: "meeting_123")
    rag_initialized = Column(Boolean, default=False, nullable=False)  # 벡터 DB 초기화 여부
    rag_initialized_at = Column(DateTime(timezone=True), nullable=True)  # 벡터 DB 초기화 시간

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    user = relationship("User", back_populates="audio_files")
    preprocessing_result = relationship("PreprocessingResult", back_populates="audio_file", uselist=False, cascade="all, delete-orphan")
    stt_results = relationship("STTResult", back_populates="audio_file", cascade="all, delete-orphan")
    diarization_results = relationship("DiarizationResult", back_populates="audio_file", cascade="all, delete-orphan")
    detected_names = relationship("DetectedName", back_populates="audio_file", cascade="all, delete-orphan")
    speaker_mappings = relationship("SpeakerMapping", back_populates="audio_file", cascade="all, delete-orphan")
    user_confirmation = relationship("UserConfirmation", back_populates="audio_file", uselist=False, cascade="all, delete-orphan")
    final_transcripts = relationship("FinalTranscript", back_populates="audio_file", cascade="all, delete-orphan")
    summaries = relationship("Summary", back_populates="audio_file", cascade="all, delete-orphan")
    todos = relationship("TodoItem", back_populates="audio_file", cascade="all, delete-orphan")
    efficiency_analysis = relationship("MeetingEfficiencyAnalysis", back_populates="audio_file", uselist=False, cascade="all, delete-orphan")
    meeting_sections = relationship("MeetingSection", back_populates="audio_file", cascade="all, delete-orphan")
    key_terms = relationship("KeyTerm", back_populates="audio_file", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<AudioFile(id={self.id}, filename={self.original_filename}, status={self.status})>"
