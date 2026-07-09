from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.core.config import settings
from pydantic import BaseModel
from datetime import datetime
import httpx
import json

router = APIRouter()

class CalendarEventRequest(BaseModel):
    summary: str
    description: str
    start_time: datetime
    end_time: datetime

async def refresh_google_token(user: User, db: Session):
    """
    Google Access Token 갱신
    """
    if not user.google_refresh_token:
        return False

    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "refresh_token": user.google_refresh_token,
        "grant_type": "refresh_token"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data=data)
        
        if response.status_code != 200:
            print(f"Failed to refresh token: {response.text}")
            return False
            
        token_data = response.json()
        new_access_token = token_data.get("access_token")
        
        if new_access_token:
            user.google_access_token = new_access_token
            db.commit()
            return True
            
    return False

@router.post("/create_event")
async def create_calendar_event(
    event: CalendarEventRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Google Calendar에 일정 추가
    """
    if not current_user.google_access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google Calendar 연동이 필요합니다."
        )

    # 이벤트 데이터 구성
    event_data = {
        "summary": event.summary,
        "description": event.description,
        "start": {
            "dateTime": event.start_time.isoformat(),
            "timeZone": "Asia/Seoul", # 한국 시간 기준
        },
        "end": {
            "dateTime": event.end_time.isoformat(),
            "timeZone": "Asia/Seoul",
        },
    }

    calendar_api_url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    
    async with httpx.AsyncClient() as client:
        # 1. 시도
        headers = {
            "Authorization": f"Bearer {current_user.google_access_token}",
            "Content-Type": "application/json"
        }
        response = await client.post(calendar_api_url, json=event_data, headers=headers)

        # 2. 토큰 만료 시 갱신 후 재시도
        if response.status_code == 401:
            print("Access token expired, refreshing...")
            refresh_success = await refresh_google_token(current_user, db)
            
            if refresh_success:
                # 갱신된 토큰으로 재시도
                headers["Authorization"] = f"Bearer {current_user.google_access_token}"
                response = await client.post(calendar_api_url, json=event_data, headers=headers)
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Google 인증이 만료되었습니다. 다시 로그인해주세요."
                )

        if response.status_code not in [200, 201]:
            print(f"Calendar API Error: {response.text}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"일정 생성 실패: {response.text}"
            )

        return response.json()
