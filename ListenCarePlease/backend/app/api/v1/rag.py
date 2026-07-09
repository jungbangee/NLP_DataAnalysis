# backend/app/api/v1/rag.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.db.base import get_db
from app.models.audio_file import AudioFile, FileStatus
from app.models.transcript import FinalTranscript
from app.models.stt import STTResult
from app.models.diarization import DiarizationResult
from app.models.tagging import SpeakerMapping
from app.services.rag_service import RAGService

router = APIRouter()
rag_service = RAGService()


class ChatRequest(BaseModel):
    """채팅 요청 모델"""
    question: str
    speaker_filter: Optional[str] = None
    k: int = 5


class ChatResponse(BaseModel):
    """채팅 응답 모델"""
    answer: str
    sources: List[dict]
    speakers: List[str]


class InitializeResponse(BaseModel):
    """초기화 응답 모델"""
    success: bool
    message: str
    total_segments: int


@router.post("/{file_id}/initialize", response_model=InitializeResponse)
async def initialize_rag(
    file_id: int,
    db: Session = Depends(get_db)
):
    """
    RAG 시스템 초기화 - 회의록을 ChromaDB에 저장

    Args:
        file_id: 오디오 파일 ID

    Returns:
        초기화 성공 여부 및 저장된 세그먼트 수
    """
    # 파일 존재 여부 확인
    audio_file = db.query(AudioFile).filter(AudioFile.id == file_id).first()
    if not audio_file:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    # 최종 회의록 조회 (FinalTranscript 우선, 없으면 태깅 결과로 동적 생성)
    final_transcripts = db.query(FinalTranscript).filter(
        FinalTranscript.audio_file_id == file_id
    ).order_by(FinalTranscript.segment_index).all()

    transcript_data = []
    
    if final_transcripts:
        # FinalTranscript가 있으면 사용
        for segment in final_transcripts:
            transcript_data.append({
                "speaker_name": segment.speaker_name,
                "speaker_label": segment.speaker_name,
                "start_time": segment.start_time,
                "end_time": segment.end_time,
                "text": segment.text
            })
    else:
        # FinalTranscript가 없으면 태깅 결과로 동적 생성 (태깅이 완료된 경우에만)
        # SpeakerMapping이 존재하는지 확인 (태깅이 시작되었는지)
        speaker_mappings_all = db.query(SpeakerMapping).filter(
            SpeakerMapping.audio_file_id == file_id
        ).all()
        
        if not speaker_mappings_all:
            raise HTTPException(
                status_code=400, 
                detail="회의록이 아직 생성되지 않았습니다. 먼저 화자 태깅을 완료해주세요."
            )
        
        # final_name이 있는 매핑 확인 (태깅 완료 여부)
        speaker_mappings = [sm for sm in speaker_mappings_all if sm.final_name and sm.final_name.strip()]
        
        # final_name이 없으면 suggested_name 사용 시도
        if not speaker_mappings:
            speaker_mappings = [sm for sm in speaker_mappings_all if sm.suggested_name and sm.suggested_name.strip()]
            if not speaker_mappings:
                raise HTTPException(
                    status_code=400, 
                    detail="회의록이 아직 생성되지 않았습니다. 먼저 화자 태깅을 완료해주세요."
                )
            # suggested_name을 final_name으로 사용
            mappings = {sm.speaker_label: sm.suggested_name for sm in speaker_mappings}
        else:
            # final_name 사용
            mappings = {sm.speaker_label: sm.final_name for sm in speaker_mappings}
        
        # STT 결과 조회
        stt_results = db.query(STTResult).filter(
            STTResult.audio_file_id == file_id
        ).order_by(STTResult.start_time).all()

        if not stt_results:
            raise HTTPException(
                status_code=400, 
                detail="회의록이 아직 생성되지 않았습니다. 먼저 파일 처리를 완료해주세요."
            )

        # Diarization 결과 조회
        diar_results = db.query(DiarizationResult).filter(
            DiarizationResult.audio_file_id == file_id
        ).order_by(DiarizationResult.start_time).all()

        # STT와 Diarization 병합하여 최종 회의록 생성
        for idx, stt in enumerate(stt_results):
            speaker_label = "UNKNOWN"
            for diar in diar_results:
                if diar.start_time <= stt.start_time < diar.end_time:
                    speaker_label = diar.speaker_label
                    break

            # final_name 또는 suggested_name 매핑 적용 (없으면 speaker_label 사용)
            speaker_name = mappings.get(speaker_label, speaker_label)

            transcript_data.append({
                "speaker_name": speaker_name,
                "speaker_label": speaker_label,
                "start_time": stt.start_time,
                "end_time": stt.end_time,
                "text": stt.text
            })
        
        # 동적 생성한 결과를 FinalTranscript에 저장 (다음번에는 바로 사용)
        for idx, data in enumerate(transcript_data):
            final_transcript = FinalTranscript(
                audio_file_id=file_id,
                segment_index=idx,
                speaker_name=data["speaker_name"],
                start_time=data["start_time"],
                end_time=data["end_time"],
                text=data["text"]
            )
            db.add(final_transcript)
        db.commit()

    if not transcript_data:
        raise HTTPException(
            status_code=400, 
            detail="회의록이 아직 생성되지 않았습니다. 먼저 화자 태깅을 완료해주세요."
        )

    try:
        # ChromaDB에 저장
        rag_service.store_transcript(str(file_id), transcript_data)

        # DB에 벡터 DB 상태 저장
        collection_name = f"meeting_{file_id}"
        audio_file.rag_collection_name = collection_name
        audio_file.rag_initialized = True
        audio_file.rag_initialized_at = datetime.now()
        db.commit()

        return InitializeResponse(
            success=True,
            message="RAG 시스템이 성공적으로 초기화되었습니다",
            total_segments=len(transcript_data)
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"RAG 초기화 실패: {str(e)}")


@router.post("/{file_id}/chat", response_model=ChatResponse)
async def chat_with_transcript(
    file_id: int,
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    """
    회의록에 대해 질문하고 답변 받기

    Args:
        file_id: 오디오 파일 ID
        request: 질문 및 필터 옵션

    Returns:
        AI 생성 답변, 관련 소스, 언급된 화자 목록
    """
    # 파일 존재 여부 확인
    audio_file = db.query(AudioFile).filter(AudioFile.id == file_id).first()
    if not audio_file:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    # 벡터 DB 초기화 상태 확인
    if not audio_file.rag_initialized:
        raise HTTPException(
            status_code=400,
            detail="벡터 DB가 초기화되지 않았습니다. 먼저 /rag/{file_id}/initialize를 호출해주세요."
        )

    # 화자 목록 조회 (자동 필터 감지용)
    speakers = db.query(FinalTranscript.speaker_name).filter(
        FinalTranscript.audio_file_id == file_id
    ).distinct().all()
    available_speakers = [speaker[0] for speaker in speakers]

    try:
        # RAG 쿼리 실행 (자동 화자 필터 감지 포함)
        result = rag_service.query_transcript(
            file_id=str(file_id),
            question=request.question,
            speaker_filter=request.speaker_filter,
            k=request.k,
            available_speakers=available_speakers
        )

        return ChatResponse(
            answer=result["answer"],
            sources=result["sources"],
            speakers=result["speakers"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG 쿼리 실패: {str(e)}")


@router.get("/{file_id}/speakers")
async def get_speakers(
    file_id: int,
    db: Session = Depends(get_db)
):
    """
    회의록의 화자 목록 조회

    Args:
        file_id: 오디오 파일 ID

    Returns:
        화자 이름 목록
    """
    # 파일 존재 여부 확인
    audio_file = db.query(AudioFile).filter(AudioFile.id == file_id).first()
    if not audio_file:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    # 화자 목록 조회 (중복 제거)
    speakers = db.query(FinalTranscript.speaker_name).filter(
        FinalTranscript.audio_file_id == file_id
    ).distinct().all()

    speaker_list = [speaker[0] for speaker in speakers]

    return {
        "file_id": file_id,
        "speakers": speaker_list,
        "total_speakers": len(speaker_list)
    }


@router.get("/{file_id}/status")
async def get_rag_status(
    file_id: int,
    db: Session = Depends(get_db)
):
    """
    RAG 초기화 상태 조회

    Args:
        file_id: 오디오 파일 ID

    Returns:
        RAG 초기화 상태 정보
    """
    # 파일 존재 여부 확인
    audio_file = db.query(AudioFile).filter(AudioFile.id == file_id).first()
    if not audio_file:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    return {
        "file_id": file_id,
        "rag_initialized": audio_file.rag_initialized or False,
        "rag_collection_name": audio_file.rag_collection_name,
        "rag_initialized_at": audio_file.rag_initialized_at.isoformat() if audio_file.rag_initialized_at else None
    }


@router.delete("/{file_id}")
async def delete_rag_collection(
    file_id: int,
    db: Session = Depends(get_db)
):
    """
    RAG 컬렉션 삭제

    Args:
        file_id: 오디오 파일 ID

    Returns:
        삭제 성공 여부
    """
    # 파일 존재 여부 확인
    audio_file = db.query(AudioFile).filter(AudioFile.id == file_id).first()
    if not audio_file:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    try:
        success = rag_service.delete_collection(str(file_id))
        if success:
            # DB 상태도 업데이트
            audio_file.rag_initialized = False
            audio_file.rag_collection_name = None
            audio_file.rag_initialized_at = None
            db.commit()
            
            return {
                "success": True,
                "message": "RAG 컬렉션이 삭제되었습니다"
            }
        else:
            raise HTTPException(status_code=500, detail="컬렉션 삭제 실패")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"삭제 중 오류 발생: {str(e)}")
