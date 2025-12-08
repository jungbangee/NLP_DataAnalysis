"""
Speaker Profile API
화자 프로필 관리 엔드포인트
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.api.deps import get_db
from app.models.speaker_profile import SpeakerProfile
from app.models.tagging import SpeakerMapping
from app.models.diarization import DiarizationResult
from app.models.audio_file import AudioFile
from app.models.stt import STTResult
from pydantic import BaseModel
from typing import List, Optional
from openai import OpenAI
from app.core.config import settings
import numpy as np


router = APIRouter()


class SaveProfileRequest(BaseModel):
    """프로필 저장 요청"""
    audio_file_id: int
    speaker_label: str  # "SPEAKER_00"
    speaker_name: str  # "김민서"


class SaveProfileResponse(BaseModel):
    """프로필 저장 응답"""
    profile_id: int
    message: str


class ProfileListResponse(BaseModel):
    """프로필 목록 응답"""
    profiles: List[dict]


@router.post("/save", response_model=SaveProfileResponse)
async def save_speaker_profile(
    request: SaveProfileRequest,
    db: Session = Depends(get_db)
):
    """
    태깅 완료 후 화자 프로필 저장
    - 음성 임베딩: diarization_results에서 평균 계산
    - 텍스트 임베딩: 발화 샘플로 OpenAI 임베딩 생성
    """
    # AudioFile 조회 (user_id 가져오기)
    audio_file = db.query(AudioFile).filter(AudioFile.id == request.audio_file_id).first()
    if not audio_file:
        raise HTTPException(status_code=404, detail="오디오 파일을 찾을 수 없습니다")

    # SpeakerMapping 조회 (final_name 확인)
    speaker_mapping = db.query(SpeakerMapping).filter(
        SpeakerMapping.audio_file_id == request.audio_file_id,
        SpeakerMapping.speaker_label == request.speaker_label
    ).first()

    if not speaker_mapping:
        raise HTTPException(status_code=404, detail="화자 매핑을 찾을 수 없습니다")

    # 이미 프로필이 있는지 확인
    existing_profile = db.query(SpeakerProfile).filter(
        SpeakerProfile.user_id == audio_file.user_id,
        SpeakerProfile.speaker_name == request.speaker_name
    ).first()

    if existing_profile:
        # 기존 프로필 업데이트 (confidence_score 증가)
        existing_profile.confidence_score += 1
        existing_profile.source_audio_file_id = request.audio_file_id
        db.commit()
        return SaveProfileResponse(
            profile_id=existing_profile.id,
            message=f"프로필 '{request.speaker_name}' 업데이트 완료 (신뢰도: {existing_profile.confidence_score})"
        )

    # 1. 음성 임베딩 평균 계산
    diar_results = db.query(DiarizationResult).filter(
        DiarizationResult.audio_file_id == request.audio_file_id,
        DiarizationResult.speaker_label == request.speaker_label
    ).all()

    if not diar_results:
        raise HTTPException(status_code=404, detail="화자 분리 결과를 찾을 수 없습니다")

    # 임베딩 평균 계산
    embeddings = [np.array(d.embedding) for d in diar_results if d.embedding]
    if embeddings:
        voice_embedding = np.mean(embeddings, axis=0).tolist()
    else:
        voice_embedding = None

    # 2. 텍스트 샘플 추출 (발화 3-5개)
    stt_results = db.query(STTResult).filter(
        STTResult.audio_file_id == request.audio_file_id
    ).order_by(STTResult.start_time).all()

    sample_texts = []
    for diar in diar_results[:5]:  # 최대 5개 세그먼트
        segment_texts = [
            stt.text for stt in stt_results
            if diar.start_time <= stt.start_time < diar.end_time
        ]
        if segment_texts:
            sample_texts.append(" ".join(segment_texts))

    # 3. 텍스트 임베딩 생성 (OpenAI)
    text_embedding = None
    if sample_texts:
        try:
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            combined_text = " ".join(sample_texts)
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=combined_text
            )
            text_embedding = response.data[0].embedding
        except Exception as e:
            print(f"⚠️ 텍스트 임베딩 생성 실패: {e}")

    # 4. 프로필 저장
    new_profile = SpeakerProfile(
        user_id=audio_file.user_id,
        speaker_name=request.speaker_name,
        voice_embedding=voice_embedding,
        text_embedding=text_embedding,
        sample_texts=sample_texts,
        source_audio_file_id=request.audio_file_id,
        confidence_score=1
    )
    db.add(new_profile)
    db.commit()
    db.refresh(new_profile)

    return SaveProfileResponse(
        profile_id=new_profile.id,
        message=f"프로필 '{request.speaker_name}' 저장 완료"
    )


@router.get("/list", response_model=ProfileListResponse)
async def list_speaker_profiles(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    사용자의 모든 화자 프로필 조회
    """
    profiles = db.query(SpeakerProfile).filter(
        SpeakerProfile.user_id == user_id
    ).order_by(SpeakerProfile.confidence_score.desc()).all()

    profile_list = []
    for profile in profiles:
        profile_list.append({
            "id": profile.id,
            "speaker_name": profile.speaker_name,
            "confidence_score": profile.confidence_score,
            "sample_count": len(profile.sample_texts) if profile.sample_texts else 0,
            "created_at": profile.created_at.isoformat() if profile.created_at else None
        })

    return ProfileListResponse(profiles=profile_list)


@router.delete("/{profile_id}")
async def delete_speaker_profile(
    profile_id: int,
    db: Session = Depends(get_db)
):
    """
    화자 프로필 삭제
    """
    profile = db.query(SpeakerProfile).filter(SpeakerProfile.id == profile_id).first()

    if not profile:
        raise HTTPException(status_code=404, detail="프로필을 찾을 수 없습니다")

    db.delete(profile)
    db.commit()

    return {"message": f"프로필 '{profile.speaker_name}' 삭제 완료"}
