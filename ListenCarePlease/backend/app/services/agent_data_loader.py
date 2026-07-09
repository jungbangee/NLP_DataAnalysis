"""
Agent 입력 데이터 로더
DB에 저장된 STT, Diarization, DetectedName 데이터를 AgentState 형식으로 변환
"""
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from app.models.audio_file import AudioFile
from app.models.stt import STTResult
from app.models.diarization import DiarizationResult
from app.models.tagging import DetectedName
from app.models.user_confirmation import UserConfirmation


def load_agent_input_data(audio_file_id: int, db: Session) -> Dict:
    """
    기존 DB 데이터를 AgentState 입력 형식으로 변환
    (processing.py의 get_merged_result 로직 재사용)

    Args:
        audio_file_id: AudioFile의 ID (DB ID)
        db: DB 세션

    Returns:
        {
            "stt_result": [{"text": str, "start": float, "end": float, "speaker": str, "has_name": bool}, ...],
            "diar_result": {"embeddings": {speaker_label: [vector]}, "turns": [...]},
            "name_mentions": [{"name": str, "context_before": [...], "context_after": [...], "time": float}, ...]
        }
    """
    # AudioFile 조회
    audio_file = db.query(AudioFile).filter(AudioFile.id == audio_file_id).first()
    if not audio_file:
        raise ValueError(f"AudioFile을 찾을 수 없습니다: {audio_file_id}")

    # 1. STTResult 조회 (시간순 정렬)
    stt_results = db.query(STTResult).filter(
        STTResult.audio_file_id == audio_file_id
    ).order_by(STTResult.start_time).all()

    # 2. DiarizationResult 조회 (시간순 정렬)
    diar_results = db.query(DiarizationResult).filter(
        DiarizationResult.audio_file_id == audio_file_id
    ).order_by(DiarizationResult.start_time).all()

    # 3. DetectedName 조회 (시간순 정렬)
    detected_names = db.query(DetectedName).filter(
        DetectedName.audio_file_id == audio_file_id
    ).order_by(DetectedName.time_detected).all()

    # 4. STT와 Diarization 병합하여 stt_result 구성
    stt_result = []
    detected_name_times = {dn.time_detected for dn in detected_names}  # 이름 언급 시간 집합
    
    for stt in stt_results:
        # 해당 STT 시간대에 겹치는 화자 찾기
        speaker_label = "UNKNOWN"
        for diar in diar_results:
            if diar.start_time <= stt.start_time < diar.end_time:
                speaker_label = diar.speaker_label
                break

        # has_name 플래그 설정 (DetectedName과 매칭)
        # 시간이 정확히 일치하지 않을 수 있으므로 근사치로 확인 (±0.5초)
        has_name = False
        for dn in detected_names:
            if abs(stt.start_time - dn.time_detected) < 0.5:
                has_name = True
                break

        stt_result.append({
            "text": stt.text,
            "start": stt.start_time,
            "end": stt.end_time,
            "speaker": speaker_label,
            "has_name": has_name
        })

    # 5. DiarizationResult에서 embeddings와 turns 구성
    embeddings = {}
    turns = []
    
    for diar in diar_results:
        # 화자별 임베딩 수집 (각 화자의 첫 번째 레코드에서 가져오기)
        if diar.speaker_label not in embeddings and diar.embedding:
            embeddings[diar.speaker_label] = diar.embedding
        
        # turns 구성
        turns.append({
            "speaker_label": diar.speaker_label,
            "start": diar.start_time,
            "end": diar.end_time
        })

    diar_result = {
        "embeddings": embeddings,
        "turns": turns
    }

    # 6. DetectedName에서 name_mentions 구성
    # 실제 이름이 언급된 문장(target)을 찾아서 포함해야 함 (대화흐름.ipynb와 동일하게)
    name_mentions = []
    for dn in detected_names:
        # time_detected와 speaker_label을 사용해서 실제 문장 찾기
        target_text = None
        target_speaker = None
        
        # STT 결과에서 해당 시간대의 문장 찾기 (±0.5초 범위)
        for stt_seg in stt_result:
            if abs(stt_seg["start"] - dn.time_detected) < 0.5:
                # speaker_label과 일치하는지 확인
                if stt_seg["speaker"] == dn.speaker_label:
                    target_text = stt_seg["text"]
                    target_speaker = stt_seg["speaker"]
                    break
        
        # target 문장이 없으면 context_before/after에서 찾기
        if not target_text and dn.context_before:
            # context_before의 마지막 항목이 target일 수 있음
            last_context = dn.context_before[-1] if isinstance(dn.context_before, list) else None
            if isinstance(last_context, dict):
                target_text = last_context.get("text", "")
                target_speaker = last_context.get("speaker", dn.speaker_label)
        
        name_mentions.append({
            "name": dn.detected_name,
            "mentioned_by": dn.speaker_label,  # 이 이름을 언급한 화자
            "time": dn.time_detected,
            "target_text": target_text or "",  # 실제 이름이 언급된 문장 (대화흐름.ipynb의 target['text'])
            "target_speaker": target_speaker or dn.speaker_label,  # target 문장의 화자
            "context_before": dn.context_before if dn.context_before else [],
            "context_after": dn.context_after if dn.context_after else []
        })

    # 7. UserConfirmation에서 참여자 이름 목록 가져오기
    user_confirmation = db.query(UserConfirmation).filter(
        UserConfirmation.audio_file_id == audio_file_id
    ).first()

    participant_names = user_confirmation.confirmed_names if user_confirmation else []

    return {
        "stt_result": stt_result,
        "diar_result": diar_result,
        "name_mentions": name_mentions,
        "participant_names": participant_names  # 참여자 이름 목록 (LLM에 전달)
    }


def load_agent_input_data_by_file_id(file_id: str, db: Session) -> Dict:
    """
    file_id (UUID)로 AudioFile을 찾아서 AgentState 입력 데이터 로드

    Args:
        file_id: 파일 ID (UUID 문자열)
        db: DB 세션

    Returns:
        load_agent_input_data와 동일한 형식
    """
    # file_id로 AudioFile 찾기
    audio_file = db.query(AudioFile).filter(
        (AudioFile.file_path.like(f"%{file_id}%")) |
        (AudioFile.original_filename.like(f"%{file_id}%"))
    ).first()

    if not audio_file:
        raise ValueError(f"AudioFile을 찾을 수 없습니다: {file_id}")

    return load_agent_input_data(audio_file.id, db)

