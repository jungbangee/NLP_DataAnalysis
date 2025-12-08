from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from pydantic import BaseModel

from app.api.deps import get_db
from app.models.audio_file import AudioFile
from app.models.tagging import SpeakerMapping
from app.models.transcript import FinalTranscript
from app.models.section import MeetingSection
from app.services.template_generator import generate_and_save_template

router = APIRouter()

class TemplateRequest(BaseModel):
    meeting_type: str = "d"  # Default: plan_design
    force_refresh: bool = False

class TemplateResponse(BaseModel):
    status: str
    data: Optional[Dict[str, Any]] = None
    message: Optional[str] = None

@router.post("/{file_id}/generate", response_model=TemplateResponse)
async def generate_template(
    file_id: int,
    request: TemplateRequest,
    db: Session = Depends(get_db)
):
    # 0. 기존 분석 결과 확인 (force_refresh가 아닐 경우)
    if not request.force_refresh:
        existing_sections = db.query(MeetingSection).filter(MeetingSection.audio_file_id == file_id).order_by(MeetingSection.section_index).all()
        if existing_sections:
            # DB에 저장된 내용을 JSON 구조로 변환하여 반환
            sections_data = []
            for s in existing_sections:
                sections_data.append({
                    "section_title": s.section_title,
                    "start_index": s.start_index,
                    "end_index": s.end_index,
                    "meeting_type": s.meeting_type,
                    "discussion_summary": s.discussion_summary,
                    "decisions": s.decisions,
                    "action_items": s.action_items
                })
            
            return TemplateResponse(
                status="success", 
                data={
                    "metadata": {"generated_by": "database", "model": "stored"},
                    "sections": sections_data
                }
            )

    try:
        # 서비스 함수 호출 (DB 저장 포함)
        result = await generate_and_save_template(db, file_id, request.meeting_type)
        return TemplateResponse(status="success", data=result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Template generation failed: {e}")
        # Return the error message to the client for debugging
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e), "detail": traceback.format_exc()}
        )
