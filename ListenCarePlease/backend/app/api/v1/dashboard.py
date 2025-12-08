"""
대시보드 API 엔드포인트
- 통계 조회
- 최근 파일 목록
- 파일 삭제
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, case
from app.api.deps import get_db
from app.models.audio_file import AudioFile, FileStatus
from app.models.tagging import SpeakerMapping
from app.models.stt import STTResult
from app.models.diarization import DiarizationResult
from app.models.efficiency import MeetingEfficiencyAnalysis
from app.models.user_confirmation import UserConfirmation
from app.models.transcript import FinalTranscript, Summary
from app.models.tagging import DetectedName
from app.models.preprocessing import PreprocessingResult
from app.models.section import MeetingSection
from app.models.keyword import KeyTerm
from app.models.todo import TodoItem
from datetime import datetime, timedelta
from typing import List, Optional
import os

router = APIRouter()


@router.get("/stats")
async def get_dashboard_stats(
    user_id: int,
    period: str = "week",  # "day", "week", "month"
    db: Session = Depends(get_db)
):
    """
    대시보드 통계 조회

    Args:
        user_id: 사용자 ID
        period: 조회 기간 ("day", "week", "month")

    Returns:
        통계 데이터
    """
    # 기간 계산
    now = datetime.now()
    if period == "day":
        start_date = now - timedelta(days=1)
        prev_start = now - timedelta(days=2)
        prev_end = now - timedelta(days=1)
    elif period == "month":
        start_date = now - timedelta(days=30)
        prev_start = now - timedelta(days=60)
        prev_end = now - timedelta(days=30)
    else:  # week
        start_date = now - timedelta(days=7)
        prev_start = now - timedelta(days=14)
        prev_end = now - timedelta(days=7)

    # 현재 기간 통계
    current_stats = db.query(
        func.count(AudioFile.id).label('total_files'),
        func.sum(case((AudioFile.status == FileStatus.PROCESSING, 1), else_=0)).label('processing'),
        func.sum(case((AudioFile.status == FileStatus.COMPLETED, 1), else_=0)).label('completed'),
        func.sum(case((AudioFile.status == FileStatus.FAILED, 1), else_=0)).label('failed'),
        func.sum(AudioFile.duration).label('total_duration')
    ).filter(
        AudioFile.user_id == user_id,
        AudioFile.created_at >= start_date
    ).first()

    # 이전 기간 통계 (비교용)
    prev_stats = db.query(
        func.count(AudioFile.id).label('total_files'),
        func.sum(AudioFile.duration).label('total_duration')
    ).filter(
        AudioFile.user_id == user_id,
        AudioFile.created_at >= prev_start,
        AudioFile.created_at < prev_end
    ).first()

    # None 처리
    total_files = current_stats.total_files or 0
    processing = current_stats.processing or 0
    completed = current_stats.completed or 0
    failed = current_stats.failed or 0
    total_duration = current_stats.total_duration or 0.0

    prev_total_files = prev_stats.total_files or 0
    prev_total_duration = prev_stats.total_duration or 0.0

    return {
        "current": {
            "total_files": total_files,
            "processing": processing,
            "completed": completed,
            "failed": failed,
            "total_duration": round(total_duration, 2)  # 초 단위
        },
        "comparison": {
            "files_diff": total_files - prev_total_files,
            "duration_diff": round(total_duration - prev_total_duration, 2)
        },
        "period": period
    }


@router.get("/recent-files")
async def get_recent_files(
    user_id: int,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """
    최근 파일 목록 조회 (참여자 정보 포함)

    Args:
        user_id: 사용자 ID
        limit: 조회 개수 (기본 10개)

    Returns:
        최근 파일 목록
    """
    # 최근 파일 조회
    files = db.query(AudioFile).filter(
        AudioFile.user_id == user_id
    ).order_by(desc(AudioFile.created_at)).limit(limit).all()

    result = []
    for file in files:
        # 참여자 정보 조회
        participants = db.query(SpeakerMapping.final_name).filter(
            SpeakerMapping.audio_file_id == file.id,
            SpeakerMapping.final_name != ""
        ).distinct().all()

        participant_names = [p.final_name for p in participants if p.final_name]

        # 시간 차이 계산 (한국어로)
        time_diff = datetime.now() - file.created_at
        if time_diff.days > 0:
            time_ago = f"{time_diff.days}일 전"
        elif time_diff.seconds // 3600 > 0:
            time_ago = f"{time_diff.seconds // 3600}시간 전"
        elif time_diff.seconds // 60 > 0:
            time_ago = f"{time_diff.seconds // 60}분 전"
        else:
            time_ago = "방금 전"

        # 태깅 완료 여부 확인 (final_name이 있는 SpeakerMapping이 있는지)
        has_tagging = db.query(SpeakerMapping).filter(
            SpeakerMapping.audio_file_id == file.id,
            SpeakerMapping.final_name != None,
            SpeakerMapping.final_name != ""
        ).first() is not None

        # file_path에서 UUID 추출 (예: /app/uploads/abc-123.m4a -> abc-123)
        file_uuid = None
        if file.file_path:
            import re
            match = re.search(r'([a-f0-9\-]{36})', file.file_path)
            if match:
                file_uuid = match.group(1)

        result.append({
            "id": file.id,
            "file_uuid": file_uuid,  # UUID 추가
            "filename": file.original_filename,
            "status": file.status.value,
            "duration": round(file.duration, 2) if file.duration else None,
            "created_at": file.created_at.isoformat(),
            "time_ago": time_ago,

            # 참여자 정보
            "participants": participant_names,
            "participant_count": len(participant_names),

            # 처리 진행 상태
            "processing_step": file.processing_step,
            "processing_progress": file.processing_progress,
            "processing_message": file.processing_message,
            "error_message": file.error_message,

            # 태깅 완료 여부
            "has_tagging": has_tagging,
            
            # 화자 정보 확정 여부
            "has_user_confirmation": db.query(UserConfirmation).filter(
                UserConfirmation.audio_file_id == file.id
            ).first() is not None
        })

    return result


@router.get("/processing-files")
async def get_processing_files(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    현재 처리 중인 파일 목록 조회

    Args:
        user_id: 사용자 ID

    Returns:
        처리 중인 파일 목록
    """
    files = db.query(AudioFile).filter(
        AudioFile.user_id == user_id,
        AudioFile.status == FileStatus.PROCESSING
    ).order_by(desc(AudioFile.created_at)).all()

    result = []
    for file in files:
        # 예상 완료 시간 계산 (간단한 추정)
        if file.processing_progress and file.processing_progress > 0:
            elapsed = (datetime.now() - file.created_at).total_seconds()
            estimated_total = (elapsed / file.processing_progress) * 100
            remaining = max(0, estimated_total - elapsed)
            estimated_completion = datetime.now() + timedelta(seconds=remaining)
        else:
            estimated_completion = None

        result.append({
            "id": file.id,
            "filename": file.original_filename,
            "status": file.status.value,
            "created_at": file.created_at.isoformat(),

            # 진행 상태
            "processing_step": file.processing_step,
            "progress": file.processing_progress,
            "message": file.processing_message,

            # 예상 완료 시간
            "estimated_completion": estimated_completion.isoformat() if estimated_completion else None
        })

    return result


@router.delete("/files/{file_id}")
async def delete_audio_file(
    file_id: int,
    db: Session = Depends(get_db)
):
    """
    오디오 파일 및 관련 데이터 삭제
    """
    # 파일 조회
    audio_file = db.query(AudioFile).filter(AudioFile.id == file_id).first()
    if not audio_file:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    # 관련 데이터 삭제 (순서 중요하지 않음, CASCADE가 없거나 불안정한 경우를 대비해 명시적 삭제)
    # 테이블이 없을 경우를 대비해 예외 처리 추가
    from sqlalchemy.exc import ProgrammingError, OperationalError

    def safe_delete(model):
        try:
            db.query(model).filter(getattr(model, 'audio_file_id', None) == file_id or getattr(model, 'file_id', None) == file_id).delete()
        except (ProgrammingError, OperationalError):
            pass # 테이블이 없으면 무시
        except Exception as e:
            print(f"Error deleting {model.__tablename__}: {e}")

    safe_delete(MeetingEfficiencyAnalysis)
    safe_delete(UserConfirmation)
    safe_delete(FinalTranscript)
    safe_delete(Summary)
    safe_delete(DetectedName)
    safe_delete(PreprocessingResult)
    safe_delete(MeetingSection)
    safe_delete(KeyTerm)
    safe_delete(TodoItem)
    
    safe_delete(STTResult)
    safe_delete(DiarizationResult)
    safe_delete(SpeakerMapping)

    # 실제 파일 삭제
    if audio_file.file_path and os.path.exists(audio_file.file_path):
        try:
            os.remove(audio_file.file_path)
        except Exception as e:
            print(f"파일 삭제 실패: {e}")

    # DB에서 삭제
    from sqlalchemy import text
    try:
        db.delete(audio_file)
        db.commit()
    except Exception as e:
        print(f"ORM 삭제 실패 (테이블 누락 가능성): {e}")
        db.rollback()
        # ORM 실패 시 Raw SQL로 강제 삭제 (CASCADE 무시하고 해당 레코드만 삭제 시도)
        try:
            db.execute(text("DELETE FROM audio_files WHERE id = :id"), {"id": file_id})
            db.commit()
            print("Raw SQL로 강제 삭제 성공")
        except Exception as sql_e:
            print(f"Raw SQL 삭제 실패: {sql_e}")
            raise HTTPException(status_code=500, detail=f"파일 삭제 중 오류가 발생했습니다: {str(sql_e)}")

    return {"message": "파일이 삭제되었습니다", "file_id": file_id}
