"""
DB에서 직접 데이터를 조회하여 임베딩이 포함된 결과를 생성하는 스크립트
"""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.db.base import SessionLocal
from app.models.audio_file import AudioFile
from app.models.stt import STTResult
from app.models.diarization import DiarizationResult
from app.models.tagging import DetectedName, SpeakerMapping
from app.models.user_confirmation import UserConfirmation

file_id = "8e6f389b-45dc-4cb3-b30c-d656b5e0bbe7"

db = SessionLocal()

try:
    # AudioFile 조회
    audio_file = db.query(AudioFile).filter(
        (AudioFile.file_path.like(f"%{file_id}%")) |
        (AudioFile.original_filename.like(f"%{file_id}%"))
    ).first()

    if not audio_file:
        print(f"파일을 찾을 수 없습니다: {file_id}")
        sys.exit(1)

    print(f"파일 찾음: {audio_file.original_filename}")

    # STT 결과 조회
    stt_results = db.query(STTResult).filter(
        STTResult.audio_file_id == audio_file.id
    ).order_by(STTResult.start_time).all()
    print(f"STT 결과: {len(stt_results)}개")

    # Diarization 결과 조회
    diar_results = db.query(DiarizationResult).filter(
        DiarizationResult.audio_file_id == audio_file.id
    ).order_by(DiarizationResult.start_time).all()
    print(f"Diarization 결과: {len(diar_results)}개")

    # 화자별 임베딩 수집
    speaker_embeddings = {}
    for diar in diar_results:
        if diar.speaker_label not in speaker_embeddings and diar.embedding:
            speaker_embeddings[diar.speaker_label] = diar.embedding
    print(f"화자별 임베딩: {len(speaker_embeddings)}개")

    # STT와 Diarization 병합
    merged_segments = []
    for stt in stt_results:
        speaker_label = "UNKNOWN"
        for diar in diar_results:
            if diar.start_time <= stt.start_time < diar.end_time:
                speaker_label = diar.speaker_label
                break

        merged_segments.append({
            "speaker": speaker_label,
            "start": stt.start_time,
            "end": stt.end_time,
            "text": stt.text
        })

    # 감지된 이름 조회
    detected_names = db.query(DetectedName.detected_name).filter(
        DetectedName.audio_file_id == audio_file.id
    ).distinct().all()
    detected_names_list = [name[0] for name in detected_names]

    # 화자 매핑 조회
    speaker_mappings = db.query(SpeakerMapping).filter(
        SpeakerMapping.audio_file_id == audio_file.id
    ).all()
    speaker_mapping_dict = {sm.speaker_label: sm.final_name for sm in speaker_mappings}

    # 사용자 확정 정보 조회
    user_confirmation = db.query(UserConfirmation).filter(
        UserConfirmation.audio_file_id == audio_file.id
    ).first()

    # 전체 결과 구성
    export_data = {
        "file_info": {
            "file_id": file_id,
            "original_filename": audio_file.original_filename,
            "duration": audio_file.duration,
            "created_at": audio_file.created_at.isoformat() if audio_file.created_at else None,
        },
        "speaker_info": {
            "speaker_count": len(set(seg["speaker"] for seg in merged_segments)),
            "detected_names": detected_names_list,
            "speaker_mappings": speaker_mapping_dict,
            "embeddings": speaker_embeddings,  # 화자별 임베딩 벡터
        },
        "user_confirmation": {
            "confirmed_speaker_count": user_confirmation.confirmed_speaker_count if user_confirmation else None,
            "confirmed_names": user_confirmation.confirmed_names if user_confirmation else None,
        },
        "segments": merged_segments,
        "total_segments": len(merged_segments),
    }

    # JSON 파일로 저장
    export_dir = Path("/app/uploads") if Path("/app/uploads").exists() else Path("uploads")
    export_dir.mkdir(exist_ok=True, parents=True)

    export_filename = f"{file_id}_merged.json"
    export_path = export_dir / export_filename

    with open(export_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)

    print(f"\n결과 파일 생성 완료: {export_path}")
    print(f"임베딩 포함: {len(speaker_embeddings)}개 화자")
    for speaker, embedding in speaker_embeddings.items():
        if embedding:
            print(f"  - {speaker}: {len(embedding)}차원 벡터")
        else:
            print(f"  - {speaker}: None")

except Exception as e:
    print(f"오류 발생: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()

