from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.api.deps import get_db
from app.models.keyword import KeyTerm
from app.models.audio_file import AudioFile

router = APIRouter()

class KeyTermResponse(BaseModel):
    id: int
    term: str
    meaning: Optional[str] = None
    glossary_display: Optional[str] = None
    synonyms: Optional[List[str]] = None
    importance: float
    first_appearance_index: Optional[int] = None

    class Config:
        from_attributes = True

@router.get("/{file_id}", response_model=List[KeyTermResponse])
async def get_keywords(file_id: int, db: Session = Depends(get_db)):
    """
    특정 파일의 핵심 용어 목록 조회
    """
    # 파일 존재 확인
    audio_file = db.query(AudioFile).filter(AudioFile.id == file_id).first()
    if not audio_file:
        raise HTTPException(status_code=404, detail="Audio file not found")

    keywords = db.query(KeyTerm).filter(
        KeyTerm.audio_file_id == file_id
    ).order_by(KeyTerm.first_appearance_index).all()

    return keywords
