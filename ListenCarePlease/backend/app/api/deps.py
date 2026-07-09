from typing import Generator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db.base import SessionLocal
from app.core.security import decode_token
from app.models.user import User

# HTTP Bearer 토큰 스키마
security = HTTPBearer()


def get_db() -> Generator:
    """데이터베이스 세션 생성"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    현재 인증된 사용자 가져오기
    Authorization: Bearer {access_token}
    """
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 정보가 유효하지 않습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 토큰 디코딩
    payload = decode_token(token)
    if payload is None:
        print(f"토큰 디코딩 실패: {token[:50]}...")
        raise credentials_exception

    # 토큰 타입 검증
    token_type = payload.get("type")
    print(f"토큰 타입: {token_type}, 페이로드: {payload}")
    if token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access Token이 필요합니다.",
        )

    # 사용자 ID 추출
    user_id_str = payload.get("sub")
    if user_id_str is None:
        print(f"사용자 ID 없음. 페이로드: {payload}")
        raise credentials_exception

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        print(f"사용자 ID 변환 실패: {user_id_str}")
        raise credentials_exception

    # 사용자 조회
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception

    # 활성화 상태 확인
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다.",
        )

    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """현재 활성화된 사용자 가져오기"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다."
        )
    return current_user
