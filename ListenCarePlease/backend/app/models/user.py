from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
import enum


class OAuthProvider(str, enum.Enum):
    """OAuth 제공자"""
    GOOGLE = "google"
    KAKAO = "kakao"
    GITHUB = "github"


class User(Base):
    """사용자 모델 (하이브리드 인증 지원)"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=True, index=True)  # nullable - 소셜 전용 계정
    password_hash = Column(String(255), nullable=True)  # nullable - 소셜 전용 계정
    full_name = Column(String(100), nullable=False)

    # OAuth 관련
    oauth_provider = Column(Enum(OAuthProvider), nullable=True)
    oauth_id = Column(String(255), nullable=True)
    
    # Google Calendar Tokens
    google_access_token = Column(String(255), nullable=True)
    google_refresh_token = Column(String(255), nullable=True)

    # 상태
    is_active = Column(Boolean, default=True, nullable=False)

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    audio_files = relationship("AudioFile", back_populates="user", cascade="all, delete-orphan")

    # 제약 조건
    __table_args__ = (
        UniqueConstraint('email', 'oauth_provider', name='uq_user_email_oauth'),
        UniqueConstraint('oauth_provider', 'oauth_id', name='uq_user_oauth_provider_id'),
    )

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, oauth_provider={self.oauth_provider})>"
