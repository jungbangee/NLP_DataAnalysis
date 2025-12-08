from sqlalchemy.orm import Session
from app.db.base import SessionLocal
from app.models.audio_file import AudioFile
from app.models.tagging import SpeakerMapping
from app.models.transcript import FinalTranscript
from app.models.section import MeetingSection
from app.agents.template_fitting_agent import run_template_fitting_agent
import asyncio

async def generate_and_save_template(db: Session, file_id: int, meeting_type: str = "d"):
    """
    템플릿 생성 및 DB 저장 로직 (동기/비동기 공용)
    """
    # 1. 파일 확인
    audio_file = db.query(AudioFile).filter(AudioFile.id == file_id).first()
    if not audio_file:
        raise ValueError(f"Audio file {file_id} not found")

    # 2. 화자 매핑 조회
    speakers = db.query(SpeakerMapping).filter(SpeakerMapping.audio_file_id == file_id).all()
    speaker_map = {s.speaker_label: s.final_name for s in speakers}

    # 3. 트랜스크립트 조회
    transcripts = db.query(FinalTranscript).filter(FinalTranscript.audio_file_id == file_id).order_by(FinalTranscript.start_time).all()
    if not transcripts:
        raise ValueError(f"Transcript for file {file_id} not found")

    transcript_segments = [
        {
            "speaker_label": t.speaker_name,
            "text": t.text,
            "start_time": t.start_time,
            "end_time": t.end_time
        }
        for t in transcripts
    ]

    # 4. 에이전트 실행
    result = await run_template_fitting_agent(
        transcript_segments=transcript_segments,
        speaker_mapping=speaker_map,
        meeting_type=meeting_type
    )

    # 5. 결과 DB 저장
    # 기존 섹션 삭제
    db.query(MeetingSection).filter(MeetingSection.audio_file_id == file_id).delete()

    if result and "sections" in result:
        for idx, sec in enumerate(result["sections"]):
            db_section = MeetingSection(
                audio_file_id=file_id,
                section_index=idx,
                section_title=sec.get("section_title"),
                start_index=sec.get("start_index", 0),
                end_index=sec.get("end_index", 0),
                meeting_type=sec.get("meeting_type"),
                discussion_summary=sec.get("discussion_summary"),
                decisions=sec.get("decisions"),
                action_items=sec.get("action_items")
            )
            db.add(db_section)
        db.commit()
    
    return result

async def run_template_generation_background(file_id: int):
    """
    백그라운드 실행용 래퍼 함수 (새로운 DB 세션 생성)
    """
    print(f"[TemplateGenerator] Starting background generation for file {file_id}")
    db = SessionLocal()
    try:
        await generate_and_save_template(db, file_id)
        print(f"[TemplateGenerator] Completed generation for file {file_id}")
    except Exception as e:
        print(f"[TemplateGenerator] Failed generation for file {file_id}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()
