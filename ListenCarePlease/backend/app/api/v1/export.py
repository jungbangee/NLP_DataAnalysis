from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.models.audio_file import AudioFile
from app.models.transcript import FinalTranscript
from app.services.export_service import create_docx, create_xlsx, create_pdf
from app.services.meeting_minutes_service import create_meeting_minutes_docx
import urllib.parse
import os

router = APIRouter()

def get_transcript_data(db: Session, file_id: int):
    audio_file = db.query(AudioFile).filter(AudioFile.id == file_id).first()
    if not audio_file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # STTResult 대신 FinalTranscript 사용
    transcripts = db.query(FinalTranscript).filter(FinalTranscript.audio_file_id == file_id).order_by(FinalTranscript.segment_index).all()
    
    transcript_data = [(t.speaker_name, t.text) for t in transcripts]
    speakers = sorted(list(set([t.speaker_name for t in transcripts])))
    
    file_info = {
        "filename": audio_file.original_filename,
        "created_at": audio_file.created_at
    }
    
    return transcript_data, speakers, file_info

@router.get("/{file_id}/docx")
async def export_docx(file_id: int, db: Session = Depends(get_db)):
    try:
        transcript_data, speakers, file_info = get_transcript_data(db, file_id)
        output = create_docx(transcript_data, speakers, file_info)
        
        filename = f"{file_info['filename']}_녹취록.docx"
        encoded_filename = urllib.parse.quote(filename)
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
        )
    except Exception as e:
        print(f"[Export Error] DOCX generation failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

@router.get("/{file_id}/xlsx")
async def export_xlsx(file_id: int, db: Session = Depends(get_db)):
    try:
        transcript_data, speakers, file_info = get_transcript_data(db, file_id)
        output = create_xlsx(transcript_data, file_info)
        
        filename = f"{file_info['filename']}_녹취록.xlsx"
        encoded_filename = urllib.parse.quote(filename)
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
        )
    except Exception as e:
        print(f"[Export Error] XLSX generation failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

@router.get("/{file_id}/pdf")
async def export_pdf(file_id: int, db: Session = Depends(get_db)):
    try:
        transcript_data, speakers, file_info = get_transcript_data(db, file_id)
        output = create_pdf(transcript_data, speakers, file_info)

        filename = f"{file_info['filename']}_녹취록.pdf"
        encoded_filename = urllib.parse.quote(filename)

        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
        )
    except Exception as e:
        print(f"[Export Error] PDF generation failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

@router.get("/{file_id}/meeting-minutes")
async def export_meeting_minutes(file_id: int, template_type: int = 4, db: Session = Depends(get_db)):
    """
    LangChain + GPT 기반 자동 회의록 생성
    회의록입력.ipynb 로직 통합

    Args:
        file_id: 오디오 파일 ID
        template_type: 템플릿 타입 (1: 기본형, 2: 의견형, 3: 결과형, 4: 상세형)
    """
    try:
        # 녹취록 데이터 가져오기
        transcript_data, speakers, file_info = get_transcript_data(db, file_id)

        # 환경변수에서 API 키 가져오기
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

        # 템플릿 파일 경로 (없으면 자동 생성)
        template_path = "/app/templates/회의록_기본양식.docx"
        if not os.path.exists(template_path):
            print("⚠️ Template not found, creating runtime template...")
            os.makedirs("/app/templates", exist_ok=True)
            # 런타임 템플릿 생성
            from app.services.export_service import create_runtime_template
            create_runtime_template(template_path)

        # 회의록 생성
        output = create_meeting_minutes_docx(
            transcript_data=transcript_data,
            speakers=speakers,
            file_info=file_info,
            template_path=template_path,
            api_key=api_key,
            form_type=template_type
        )

        # 템플릿 타입별 파일명
        type_names = {1: "기본형", 2: "의견형", 3: "결과형", 4: "상세형"}
        type_name = type_names.get(template_type, "상세형")
        filename = f"{file_info['filename']}_회의록_{type_name}.docx"
        encoded_filename = urllib.parse.quote(filename)

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
        )
    except Exception as e:
        print(f"[Export Error] Meeting minutes generation failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Meeting minutes generation failed: {str(e)}")
