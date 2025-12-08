from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AudioFileUploadResponse(BaseModel):
    """파일 업로드 응답"""
    file_id: str
    filename: str
    message: str


class AudioFileProcessRequest(BaseModel):
    """파일 처리 요청"""
    file_id: str


class AudioFileProcessResponse(BaseModel):
    """파일 처리 응답 (Mock)"""
    file_id: str
    status: str
    message: str


class AudioFileStatusResponse(BaseModel):
    """파일 상태 조회 응답"""
    file_id: str
    filename: str
    status: str
    duration: Optional[float] = None
    created_at: datetime
