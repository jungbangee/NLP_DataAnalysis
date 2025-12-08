from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, UniqueConstraint, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class DetectedName(Base):
    """감지된 이름 모델 (I,O.md Step 5a~5c) - 멀티턴 LLM 추론"""
    __tablename__ = "detected_names"

    id = Column(Integer, primary_key=True, index=True)
    audio_file_id = Column(Integer, ForeignKey("audio_files.id", ondelete="CASCADE"), nullable=False, index=True)

    # 감지 정보
    detected_name = Column(String(100), nullable=False, index=True)  # "민서씨", "김팀장님" 등
    speaker_label = Column(String(50), nullable=False)  # SPEAKER_00 등 (이 이름이 누구를 가리키는지)
    time_detected = Column(Float, nullable=False)  # 이름이 언급된 시간 (초)

    # 신뢰도 정보
    confidence = Column(Float, nullable=True)  # 해당 언급의 신뢰도 (0.0 ~ 1.0)
    similarity_score = Column(Float, nullable=True)  # 음성 임베딩 유사도 (동일인 판별용)

    # 멀티턴 LLM 추론 정보
    context_before = Column(JSON, nullable=True)  # 이름 언급 전 5문장 문맥
    context_after = Column(JSON, nullable=True)  # 이름 언급 후 5문장 문맥
    llm_reasoning = Column(Text, nullable=True)  # LLM 추론 근거
    is_consistent = Column(Boolean, nullable=True)  # 이전 추론과 일치 여부

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    audio_file = relationship("AudioFile", back_populates="detected_names")

    def __repr__(self):
        return f"<DetectedName(id={self.id}, name='{self.detected_name}', speaker={self.speaker_label}, consistent={self.is_consistent})>"


class SpeakerMapping(Base):
    """화자 태깅 결과 모델 (I,O.md Step 5d~5e) - 하이브리드 방식"""
    __tablename__ = "speaker_mappings"

    id = Column(Integer, primary_key=True, index=True)
    audio_file_id = Column(Integer, ForeignKey("audio_files.id", ondelete="CASCADE"), nullable=False, index=True)

    # 화자 정보
    speaker_label = Column(String(50), nullable=False)  # SPEAKER_00, SPEAKER_01, ...

    # 방식 1: 이름 기반 태깅 (Multi-turn LLM)
    suggested_name = Column(String(100), nullable=True)  # 시스템이 제안한 이름 (nullable)
    name_confidence = Column(Float, nullable=True)  # 이름 태깅 신뢰도 (멀티턴 LLM 최종 스코어)
    name_mentions = Column(Integer, default=0, nullable=False)  # 이름 언급 횟수 (0이면 이름 감지 안됨)

    # 방식 2: 역할 기반 클러스터링
    suggested_role = Column(String(50), nullable=True)  # 시스템 제안 역할 (진행자, 발표자 등)
    role_confidence = Column(Float, nullable=True)  # 역할 추론 신뢰도

    # 방식 3: 닉네임 태깅 (LLM 기반)
    nickname = Column(String(100), nullable=True)  # LLM이 생성한 닉네임 (예: "진행 담당자", "기술 전문가")
    nickname_metadata = Column(JSON, nullable=True)  # 닉네임 생성 메타데이터 (display_label, one_liner, keywords 등)

    # 품질 플래그
    conflict_detected = Column(Boolean, default=False, nullable=False)  # 모순 발견 여부
    needs_manual_review = Column(Boolean, default=False, nullable=False)  # 수동 확인 필요

    # 최종 결과
    final_name = Column(String(100), nullable=False)  # 사용자가 확정한 최종 이름

    # 메타데이터
    is_modified = Column(Boolean, default=False, nullable=False)  # 사용자가 수정했는지 여부

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    audio_file = relationship("AudioFile", back_populates="speaker_mappings")

    # 제약 조건: 같은 오디오 파일에서 같은 화자 레이블은 한 번만
    __table_args__ = (
        UniqueConstraint('audio_file_id', 'speaker_label', name='uq_speaker_mapping_audio_speaker'),
    )

    def __repr__(self):
        return f"<SpeakerMapping(id={self.id}, speaker={self.speaker_label}, name='{self.suggested_name}' (conf={self.name_confidence}), nickname='{self.nickname}', role='{self.suggested_role}' (conf={self.role_confidence}), final='{self.final_name}', conflict={self.conflict_detected})>"
