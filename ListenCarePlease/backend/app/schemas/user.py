from pydantic import BaseModel, EmailStr, validator
from typing import Optional
from datetime import datetime


# 회원가입 요청
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('비밀번호는 최소 8자 이상이어야 합니다.')
        return v


# 로그인 요청
class UserLogin(BaseModel):
    email: EmailStr
    password: str


# 토큰 응답
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# 토큰 데이터
class TokenData(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None


# 사용자 응답
class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    is_active: bool
    created_at: datetime
    oauth_provider: Optional[str] = None

    class Config:
        from_attributes = True


# Refresh Token 요청
class RefreshTokenRequest(BaseModel):
    refresh_token: str


# OAuth 콜백 응답
class OAuthCallbackResponse(BaseModel):
    code: str
    state: Optional[str] = None
