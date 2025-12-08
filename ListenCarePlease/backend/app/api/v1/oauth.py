from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import httpx
from app.api.deps import get_db
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.models.user import User
from app.schemas.user import Token

router = APIRouter()


# ============================================
# Google OAuth
# ============================================

@router.get("/auth/google/connect")
async def google_connect(
    redirect_url: str = "http://localhost:3000",
    token: str = None,
    db: Session = Depends(get_db)
):
    """
    구글 계정 연동 시작 (로그인된 사용자 전용)
    - state에 user_id를 담아서 보냄
    - window.location.href로 이동하므로 Authorization 헤더 대신 query param으로 token을 받음
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth가 설정되지 않았습니다."
        )

    # 토큰 검증 및 사용자 추출
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 토큰이 필요합니다."
        )
    
    from app.core.security import decode_token
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다."
        )
        
    user_id = int(payload.get("sub"))
    current_user = db.query(User).filter(User.id == user_id).first()
    
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다."
        )

    # 캘린더 권한 추가
    scope = "openid email profile https://www.googleapis.com/auth/calendar.events"
    
    # state 생성 (user_id와 redirect_url 포함)
    state_data = {
        "user_id": current_user.id,
        "redirect_url": redirect_url,
        "type": "connect"
    }
    # 간단한 base64 인코딩 (실제 운영 시에는 서명된 토큰 사용 권장)
    import base64
    import json
    state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

    google_auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={settings.GOOGLE_CLIENT_ID}"
        f"&redirect_uri={settings.GOOGLE_REDIRECT_URI}"
        "&response_type=code"
        f"&scope={scope}"
        "&access_type=offline"
        "&prompt=consent"
        f"&state={state}"
    )

    return RedirectResponse(url=google_auth_url)


@router.get("/auth/google/callback")
async def google_callback(code: str, state: str = None, db: Session = Depends(get_db)):
    """
    구글 OAuth 콜백
    - 인증 코드로 액세스 토큰 받기
    - 사용자 정보 조회
    - state가 있으면 기존 계정 연동, 없으면 로그인/회원가입
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth가 설정되지 않았습니다."
        )

    # 1. 인증 코드로 액세스 토큰 받기
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code"
    }

    async with httpx.AsyncClient() as client:
        token_response = await client.post(token_url, data=token_data)

        if token_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google 토큰 발급 실패"
            )

        token_json = token_response.json()
        access_token = token_json.get("access_token")
        refresh_token = token_json.get("refresh_token")

        # 2. 액세스 토큰으로 사용자 정보 조회
        userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        headers = {"Authorization": f"Bearer {access_token}"}

        userinfo_response = await client.get(userinfo_url, headers=headers)

        if userinfo_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google 사용자 정보 조회 실패"
            )

        userinfo = userinfo_response.json()

    # 3. 계정 연동 처리 (state 확인)
    if state:
        try:
            import base64
            import json
            state_data = json.loads(base64.urlsafe_b64decode(state).decode())
            
            if state_data.get("type") == "connect" and state_data.get("user_id"):
                user_id = state_data["user_id"]
                redirect_url = state_data.get("redirect_url", "http://localhost:3000")
                
                # 기존 사용자 찾기
                user = db.query(User).filter(User.id == user_id).first()
                if not user:
                    raise HTTPException(status_code=404, detail="User not found")
                
                # 토큰 업데이트 (연동)
                user.google_access_token = access_token
                if refresh_token:
                    user.google_refresh_token = refresh_token
                db.commit()
                
                # 원래 페이지로 리다이렉트
                return RedirectResponse(url=redirect_url)
                
        except Exception as e:
            print(f"State decoding error: {e}")
            # 에러 발생 시 일반 로그인 흐름으로 진행하거나 에러 반환
            pass

    # 4. 일반 로그인/회원가입 처리
    email = userinfo.get("email")
    name = userinfo.get("name")
    google_id = userinfo.get("id")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이메일 정보를 가져올 수 없습니다."
        )

    user = db.query(User).filter(
        User.email == email,
        User.oauth_provider == "google"
    ).first()

    if not user:
        user = User(
            email=email,
            full_name=name or email.split("@")[0],
            oauth_provider="google",
            oauth_id=google_id,
            is_active=True,
            password_hash=None,
            google_access_token=access_token,
            google_refresh_token=refresh_token
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.google_access_token = access_token
        if refresh_token:
            user.google_refresh_token = refresh_token
        db.commit()

    access_token_jwt = create_access_token(data={"sub": str(user.id), "email": user.email})
    refresh_token_jwt = create_refresh_token(data={"sub": str(user.id), "email": user.email})

    frontend_url = f"http://localhost:3000/oauth/callback?access_token={access_token_jwt}&refresh_token={refresh_token_jwt}"
    return RedirectResponse(url=frontend_url)


# ============================================
# Kakao OAuth
# ============================================

@router.get("/auth/kakao/login")
async def kakao_login():
    """
    카카오 로그인 시작
    - 카카오 OAuth 동의 화면으로 리다이렉트
    """
    if not settings.KAKAO_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Kakao OAuth가 설정되지 않았습니다."
        )

    kakao_auth_url = (
        "https://kauth.kakao.com/oauth/authorize"
        f"?client_id={settings.KAKAO_CLIENT_ID}"
        f"&redirect_uri={settings.KAKAO_REDIRECT_URI}"
        "&response_type=code"
    )

    return RedirectResponse(url=kakao_auth_url)


@router.get("/auth/kakao/callback")
async def kakao_callback(code: str, db: Session = Depends(get_db)):
    """
    카카오 OAuth 콜백
    - 인증 코드로 액세스 토큰 받기
    - 사용자 정보 조회
    - 기존 사용자면 로그인, 신규면 회원가입
    """
    if not settings.KAKAO_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Kakao OAuth가 설정되지 않았습니다."
        )

    # 1. 인증 코드로 액세스 토큰 받기
    token_url = "https://kauth.kakao.com/oauth/token"
    token_data = {
        "grant_type": "authorization_code",
        "client_id": settings.KAKAO_CLIENT_ID,
        "redirect_uri": settings.KAKAO_REDIRECT_URI,
        "code": code
    }

    # Client Secret이 있으면 추가
    if settings.KAKAO_CLIENT_SECRET:
        token_data["client_secret"] = settings.KAKAO_CLIENT_SECRET

    async with httpx.AsyncClient() as client:
        token_response = await client.post(token_url, data=token_data)

        if token_response.status_code != 200:
            # 상세 에러 로깅
            error_detail = token_response.json() if token_response.text else "Unknown error"
            print(f"Kakao token error: {error_detail}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Kakao 토큰 발급 실패: {error_detail}"
            )

        token_json = token_response.json()
        access_token = token_json.get("access_token")

        # 2. 액세스 토큰으로 사용자 정보 조회
        userinfo_url = "https://kapi.kakao.com/v2/user/me"
        headers = {"Authorization": f"Bearer {access_token}"}

        userinfo_response = await client.get(userinfo_url, headers=headers)

        if userinfo_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Kakao 사용자 정보 조회 실패"
            )

        userinfo = userinfo_response.json()

    # 3. 사용자 정보 추출
    kakao_id = str(userinfo.get("id"))
    kakao_account = userinfo.get("kakao_account", {})
    email = kakao_account.get("email")
    profile = kakao_account.get("profile", {})
    name = profile.get("nickname")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이메일 정보를 가져올 수 없습니다. 카카오 계정에서 이메일 제공 동의가 필요합니다."
        )

    # 4. 기존 사용자 확인
    user = db.query(User).filter(
        User.email == email,
        User.oauth_provider == "kakao"
    ).first()

    if not user:
        # 신규 사용자 - 회원가입
        user = User(
            email=email,
            full_name=name or email.split("@")[0],
            oauth_provider="kakao",
            oauth_id=kakao_id,
            is_active=True,
            password_hash=None
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # 5. JWT 토큰 발급
    access_token_jwt = create_access_token(data={"sub": str(user.id), "email": user.email})
    refresh_token_jwt = create_refresh_token(data={"sub": str(user.id), "email": user.email})

    # 6. 프론트엔드로 리다이렉트 (토큰을 URL 파라미터로 전달)
    frontend_url = f"http://localhost:3000/oauth/callback?access_token={access_token_jwt}&refresh_token={refresh_token_jwt}"
    return RedirectResponse(url=frontend_url)
