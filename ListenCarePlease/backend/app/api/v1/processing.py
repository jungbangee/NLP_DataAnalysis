"""
오디오 처리 API 엔드포인트
- 전처리 (Step 2)
- STT (Step 3)
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
import torch.serialization
if not hasattr(torch.serialization, "safe_globals"):
    torch.serialization.safe_globals = []
from pathlib import Path
from typing import Any, Dict
from app.services.preprocessing import preprocess_audio
from app.services.stt import run_stt_pipeline
from app.services.diarization import run_diarization, merge_stt_with_diarization
from app.services.ner_service import get_ner_service
from app.core.config import settings
from app.core.device import get_device
import json
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy import func
from app.api.deps import get_db, get_current_user
from fastapi import Depends
from app.models.audio_file import AudioFile, FileStatus
from app.models.preprocessing import PreprocessingResult
from app.models.stt import STTResult
from app.models.diarization import DiarizationResult
from app.models.tagging import DetectedName, SpeakerMapping
from app.models.user_confirmation import UserConfirmation


router = APIRouter()

# 처리 상태 저장 (실제로는 DB 사용)
PROCESSING_STATUS: Dict[str, dict] = {}


def process_audio_pipeline(
    file_id: str,
    user_id: int,
    whisper_mode: str = "local",
    diarization_mode: str = "senko",
    skip_stt: bool = False
):
    """
    백그라운드에서 오디오 처리 파이프라인 실행

    Args:
        file_id: 파일 ID
        user_id: 사용자 ID
        whisper_mode: Whisper 모드 ("local" 또는 "api")
        diarization_mode: 화자 분리 모델 ("senko" 또는 "nemo")
    """
    # 백그라운드 태스크용 새 DB 세션 생성
    from app.db.base import SessionLocal
    db = SessionLocal()

    try:
        # 디바이스 자동 감지
        device = get_device()

        # 모델 크기 고정
        model_size = "large-v3"

        # 1) 파일 경로 가져오기 + DB에서 AudioFile 찾기
        upload_dir = Path("/app/uploads")
        input_files = list(upload_dir.glob(f"{file_id}.*"))
        if not input_files:
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_id}")
        input_path = input_files[0]

        # DB에서 AudioFile 찾기 또는 생성
        audio_file = db.query(AudioFile).filter(
            (AudioFile.file_path.like(f"%{file_id}%")) |
            (AudioFile.original_filename.like(f"%{file_id}%"))
        ).first()

        if not audio_file:
            # upload.py의 UPLOADED_FILES에서 원본 파일명 가져오기
            from app.api.v1.upload import UPLOADED_FILES
            original_name = UPLOADED_FILES.get(file_id, {}).get("filename", input_path.name)

            # 새 파일이면 생성
            audio_file = AudioFile(
                user_id=user_id,
                original_filename=original_name,
                file_path=str(input_path),
                file_size=input_path.stat().st_size,
                mimetype="audio/wav",
                status=FileStatus.PROCESSING
            )
            db.add(audio_file)
            db.flush()

        # 상태 업데이트: 전처리 시작
        audio_file.status = FileStatus.PROCESSING
        audio_file.processing_step = "preprocessing"
        audio_file.processing_progress = 10
        audio_file.processing_message = "전처리 중..."
        db.commit()

        PROCESSING_STATUS[file_id] = {
            "status": "preprocessing",
            "step": "전처리 중...",
            "progress": 10,
            "device": device,
            "model_size": model_size,
        }

        # 작업 디렉토리 생성
        work_dir = Path(f"/app/temp/{file_id}")
        work_dir.mkdir(parents=True, exist_ok=True)

        # 2) 전처리
        preprocessed_path = work_dir / "preprocessed.wav"
        _, original_dur, processed_dur = preprocess_audio(input_path, preprocessed_path)

        # 상태 업데이트: 전처리 완료
        audio_file.duration = original_dur
        audio_file.processing_step = "preprocessing_complete"
        audio_file.processing_progress = 30
        audio_file.processing_message = "전처리 완료"
        db.commit()

        PROCESSING_STATUS[file_id] = {
            "status": "preprocessing",
            "step": "전처리 완료",
            "progress": 30,
            "original_duration": original_dur,
            "processed_duration": processed_dur,
        }

        # 3) STT
        use_local = whisper_mode == "local"
        stt_method = f"{'로컬' if use_local else 'API'} Whisper ({model_size})"

        # 상태 업데이트: STT 시작
        audio_file.processing_step = "stt"
        audio_file.processing_progress = 40
        audio_file.processing_message = f"STT 진행 중... ({stt_method})"
        db.commit()

        PROCESSING_STATUS[file_id] = {
            "status": "stt",
            "step": f"STT 진행 중... ({stt_method})",
            "progress": 40,
        }

        # Whisper 전사 (로컬 또는 API)
        # Whisper 전사 (로컬 또는 API)
        if skip_stt:
            print("⏩ STT 건너뛰기 (기존 결과 사용)")
            # 기존 파일 찾기
            possible_files = [
                work_dir / "transcript.txt",
                work_dir / f"{file_id}_transcript.txt",
                work_dir / "final_transcript.txt"
            ]
            final_txt = None
            for p in possible_files:
                if p.exists():
                    final_txt = p
                    break
            
            if not final_txt:
                print("⚠️ 기존 전사 파일을 찾을 수 없어 STT를 실행합니다.")
                final_txt = run_stt_pipeline(
                    preprocessed_path,
                    work_dir,
                    openai_api_key=settings.OPENAI_API_KEY if not use_local else None,
                    use_local_whisper=use_local,
                    model_size=model_size,
                    device=device
                )
        else:
            final_txt = run_stt_pipeline(
                preprocessed_path,
                work_dir,
                openai_api_key=settings.OPENAI_API_KEY if not use_local else None,
                use_local_whisper=use_local,
                model_size=model_size,
                device=device
            )

        # STT 완료 후 메모리 정리 (Diarization 전 메모리 확보)
        print("🧹 STT 완료, 메모리 정리 중...")
        import gc
        import torch
        gc.collect()  # Python 가비지 컬렉션 강제 실행
        if torch.cuda.is_available():
            torch.cuda.empty_cache()  # CUDA 캐시 정리
        print("✅ 메모리 정리 완료")

        # --- [Keyword Extraction Start] ---
        # STT 텍스트 확보
        full_transcript_text = final_txt.read_text(encoding='utf-8')
        
        # 키워드 추출을 위한 별도 스레드 시작 (Diarization과 병렬 실행)
        import threading
        import asyncio
        from app.services.keyword_extractor import extract_keywords_from_text, save_keywords_to_db

        keyword_extraction_result = {"keywords": []}
        
        def run_keyword_extraction_thread(text, result_container):
            try:
                # 새 이벤트 루프 생성 (스레드 내에서 비동기 실행)
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                keywords = loop.run_until_complete(extract_keywords_from_text(text))
                result_container["keywords"] = keywords
                loop.close()
                print(f"✅ 키워드 추출 완료: {len(keywords)}개")
            except Exception as e:
                print(f"⚠️ 키워드 추출 실패: {e}")

        keyword_thread = threading.Thread(
            target=run_keyword_extraction_thread,
            args=(full_transcript_text, keyword_extraction_result)
        )
        keyword_thread.start()
        print("🚀 키워드 추출 스레드 시작 (병렬 실행)")
        # --- [Keyword Extraction End] ---

        # 4) Diarization (화자 분리)
        diarization_method = "Senko" if diarization_mode == "senko" else "NeMo"

        # 상태 업데이트: Diarization 시작
        audio_file.processing_step = "diarization"
        audio_file.processing_progress = 70
        audio_file.processing_message = f"화자 분리 중... ({diarization_method})"
        db.commit()

        PROCESSING_STATUS[file_id] = {
            "status": "diarization",
            "step": f"화자 분리 중... ({diarization_method})",
            "progress": 70,
        }

        try:
            # 사용자 확정 화자 수 확인
            confirmed_speaker_count = None
            user_confirmation = db.query(UserConfirmation).filter(
                UserConfirmation.audio_file_id == audio_file.id
            ).first()
            
            if user_confirmation and user_confirmation.confirmed_speaker_count:
                confirmed_speaker_count = user_confirmation.confirmed_speaker_count
                print(f"🔍 사용자 확정 화자 수 적용: {confirmed_speaker_count}명")

            diarization_result = run_diarization(
                preprocessed_path,
                device=device,
                mode=diarization_mode,
                num_speakers=confirmed_speaker_count
            )

            # Diarization 결과 저장
            diarization_json = work_dir / "diarization_result.json"
            with open(diarization_json, 'w', encoding='utf-8') as f:
                json.dump(diarization_result, f, ensure_ascii=False, indent=2)

            # STT 결과 파싱
            stt_segments = []
            for line in full_transcript_text.splitlines():
                if line.strip():
                    # [00:00:00.000 - 00:00:02.800] 텍스트 형식 파싱
                    import re
                    match = re.match(r'\[(\d{2}:\d{2}:\d{2}\.\d{3}) - (\d{2}:\d{2}:\d{2}\.\d{3})\] (.+)', line)
                    if match:
                        start_str, end_str, text = match.groups()
                        # 시간을 초로 변환
                        def time_to_seconds(t):
                            h, m, s = t.split(':')
                            return int(h) * 3600 + int(m) * 60 + float(s)

                        stt_segments.append({
                            "text": text,
                            "start": time_to_seconds(start_str),
                            "end": time_to_seconds(end_str)
                        })

            # STT + Diarization 병합
            merged_result = merge_stt_with_diarization(stt_segments, diarization_result)

            # 병합 결과 저장
            merged_json = work_dir / "merged_result.json"
            with open(merged_json, 'w', encoding='utf-8') as f:
                json.dump(merged_result, f, ensure_ascii=False, indent=2)

        except Exception as diarization_error:
            import traceback
            print(f"⚠️ Diarization failed: {diarization_error}")
            print(traceback.format_exc())
            # Diarization 실패해도 STT 결과는 유지
            diarization_result = None
            merged_result = None

        # 5) NER (이름 추출 및 군집화) + 닉네임 태깅 (동시 처리)
        # 상태 업데이트: NER 시작
        audio_file.processing_step = "ner"
        audio_file.processing_progress = 85
        audio_file.processing_message = "이름 및 닉네임 추출 중..."
        db.commit()

        PROCESSING_STATUS[file_id] = {
            "status": "ner",
            "step": "이름 및 닉네임 추출 중...",
            "progress": 80,
        }

        ner_result = None
        nickname_result = None
        try:
            if merged_result:
                # NER 서비스 가져오기 (이름과 닉네임을 함께 처리)
                ner_service = get_ner_service()

                # NER 처리 (내부에서 닉네임도 함께 처리)
                ner_result = ner_service.process_segments(merged_result)

                # 닉네임 결과 추출
                nickname_result = ner_result.get('nicknames', {})

                # NER 결과 저장
                ner_json = work_dir / "ner_result.json"
                with open(ner_json, 'w', encoding='utf-8') as f:
                    json.dump(ner_result, f, ensure_ascii=False, indent=2)

                print(f"✅ NER 완료: {len(ner_result['final_namelist'])}개 대표명 추출")
                if nickname_result:
                    print(f"✅ 닉네임 태깅 완료: {len(nickname_result)}개 화자")

        except Exception as ner_error:
            print(f"⚠️ NER failed: {ner_error}")
            # NER 실패해도 병합 결과는 유지
            ner_result = None
            nickname_result = None

        # 6) DB 저장
        # 상태 업데이트: DB 저장 시작
        audio_file.processing_step = "saving"
        audio_file.processing_progress = 90
        audio_file.processing_message = "DB 저장 중..."
        db.commit()

        PROCESSING_STATUS[file_id] = {
            "status": "saving",
            "step": "DB 저장 중...",
            "progress": 90,
        }

        # DB 저장 시작
        if db:
            try:
                from app.models.diarization import DiarizationResult
                from app.models.tagging import SpeakerMapping

                audio_file_id_db = audio_file.id

                # 6-1) 기존 결과 삭제 (중복 방지)
                # 재분석 시 기존 데이터를 지우고 새로 저장해야 함
                print(f"🧹 기존 분석 결과 삭제 중: audio_file_id={audio_file_id_db}")
                db.query(STTResult).filter(STTResult.audio_file_id == audio_file_id_db).delete()
                db.query(DiarizationResult).filter(DiarizationResult.audio_file_id == audio_file_id_db).delete()
                db.query(DetectedName).filter(DetectedName.audio_file_id == audio_file_id_db).delete()
                # SpeakerMapping은 사용자 확정 정보가 있을 수 있으므로 주의해야 하지만,
                # 재분석(Diarization 다시 함)의 경우 화자 레이블이 바뀌므로 초기화하는 것이 맞음
                # 단, UserConfirmation은 유지됨
                db.query(SpeakerMapping).filter(SpeakerMapping.audio_file_id == audio_file_id_db).delete()
                db.flush()

                # 6-2) STTResult 저장 (merged_result의 각 세그먼트)
                if merged_result:
                    for idx, segment in enumerate(merged_result):
                        stt_record = STTResult(
                            audio_file_id=audio_file_id_db,
                            word_index=idx,
                            text=segment.get("text", ""),
                            start_time=segment.get("start", 0.0),
                            end_time=segment.get("end", 0.0),
                            confidence=None  # Whisper doesn't provide word-level confidence
                        )
                        db.add(stt_record)

                # 6-3) DiarizationResult 저장 (화자별 임베딩)
                if diarization_result and 'turns' in diarization_result:
                    for segment in diarization_result['turns']:
                        speaker_label = segment.get('speaker_label', 'UNKNOWN')

                        # 해당 화자의 임베딩 가져오기
                        embeddings = diarization_result.get('embeddings', {})
                        embedding_vector = embeddings.get(speaker_label)

                        diar_record = DiarizationResult(
                            audio_file_id=audio_file_id_db,
                            speaker_label=speaker_label,
                            start_time=segment.get('start', 0.0),
                            end_time=segment.get('end', 0.0),
                            embedding=embedding_vector  # JSON 형태로 저장
                        )
                        db.add(diar_record)

                # 6-4) DetectedName 저장 (NER로 감지된 이름들 - has_name: true인 세그먼트)
                if ner_result:
                    segments_with_names = ner_result.get('segments_with_names', [])

                    # 이름이 감지된 세그먼트들만 필터링
                    for idx, segment in enumerate(segments_with_names):
                        if segment.get('has_name', False) and segment.get('name'):
                            # 앞뒤 5문장 문맥 추출 (I,O.md 5a~5c)
                            context_before_idx = max(0, idx - 5)
                            context_after_idx = min(len(segments_with_names), idx + 6)

                            context_before = [
                                {
                                    "index": i - idx,
                                    "speaker": seg.get("speaker"),
                                    "text": seg.get("text"),
                                    "time": seg.get("start")
                                }
                                for i, seg in enumerate(segments_with_names[context_before_idx:idx], start=context_before_idx)
                            ]

                            context_after = [
                                {
                                    "index": i - idx,
                                    "speaker": seg.get("speaker"),
                                    "text": seg.get("text"),
                                    "time": seg.get("start")
                                }
                                for i, seg in enumerate(segments_with_names[idx+1:context_after_idx], start=idx+1)
                            ]

                            # 이 세그먼트에서 감지된 각 이름에 대해 레코드 생성
                            for detected_name in segment['name']:
                                name_record = DetectedName(
                                    audio_file_id=audio_file_id_db,
                                    detected_name=detected_name,
                                    speaker_label=segment.get('speaker', 'UNKNOWN'),
                                    time_detected=segment.get('start', 0.0),
                                    confidence=None,  # NER 신뢰도 (현재 미구현)
                                    similarity_score=None,
                                    context_before=context_before,  # 앞 5문장 (I,O.md 참조)
                                    context_after=context_after,   # 뒤 5문장 (I,O.md 참조)
                                    llm_reasoning=None,  # 멀티턴 LLM 추론 결과 (향후 구현)
                                    is_consistent=None   # 이전 추론과 일치 여부 (향후 구현)
                                )
                                db.add(name_record)

                # 6-5) SpeakerMapping 저장 (화자별 초기 레코드만 생성, 매핑은 나중에)
                if diarization_result:
                    # 화자별 고유 레이블 추출
                    speaker_labels = list(diarization_result.get('embeddings', {}).keys())

                    # 각 화자에 대해 SpeakerMapping 생성 (초기 제안 없이)
                    for speaker_label in speaker_labels:
                        # 이미 존재하는지 확인 (중복 방지)
                        existing = db.query(SpeakerMapping).filter(
                            SpeakerMapping.audio_file_id == audio_file_id_db,
                            SpeakerMapping.speaker_label == speaker_label
                        ).first()

                        if not existing:
                            # 닉네임 정보 가져오기 (NER 결과에서)
                            nickname_info = nickname_result.get(speaker_label) if nickname_result else None
                            
                            mapping = SpeakerMapping(
                                audio_file_id=audio_file_id_db,
                                speaker_label=speaker_label,
                                suggested_name=None,  # 초기 제안 없음 (향후 LLM이 추론)
                                name_confidence=None,
                                name_mentions=0,
                                suggested_role=None,
                                role_confidence=None,
                                nickname=nickname_info.get('nickname') if nickname_info else None,
                                nickname_metadata=nickname_info.get('nickname_metadata') if nickname_info else None,
                                conflict_detected=False,
                                needs_manual_review=True,  # 기본적으로 사용자 확인 필요
                                final_name="",  # 사용자가 확정 전까지 빈 값
                                is_modified=False
                            )
                            db.add(mapping)
                        elif nickname_result and speaker_label in nickname_result:
                            # 기존 레코드가 있으면 닉네임 정보만 업데이트 (NER 결과에서)
                            nickname_info = nickname_result[speaker_label]
                            existing.nickname = nickname_info.get('nickname')
                            existing.nickname_metadata = nickname_info.get('nickname_metadata')

                # 6-6) 키워드 저장 (스레드 조인 및 저장)
                print("⏳ 키워드 추출 스레드 대기 중...")
                keyword_thread.join(timeout=60) # 최대 60초 대기 (이미 완료되었을 가능성 높음)
                if keyword_thread.is_alive():
                    print("⚠️ 키워드 추출 스레드가 아직 실행 중입니다. (타임아웃)")
                
                extracted_keywords = keyword_extraction_result.get("keywords", [])
                if extracted_keywords and merged_result:
                    print(f"💾 키워드 {len(extracted_keywords)}개 DB 저장 중...")
                    try:
                        save_keywords_to_db(db, audio_file_id_db, extracted_keywords, merged_result)
                    except Exception as kw_error:
                        print(f"⚠️ 키워드 저장 실패 (무시함): {kw_error}")
                        # 키워드 저장 실패는 전체 트랜잭션을 롤백하지 않도록 함
                else:
                    print("⚠️ 저장할 키워드가 없거나 병합 결과가 없습니다.")

                # 6-7) AudioFile 상태 업데이트: 완료
                audio_file.status = FileStatus.COMPLETED
                audio_file.processing_step = "completed"
                audio_file.processing_progress = 100
                audio_file.processing_message = "처리 완료"

                # 커밋
                db.commit()
                print(f"✅ DB 저장 완료: audio_file_id={audio_file_id_db}")

                # 완료 시 메모리에서 제거하여 DB 조회를 유도 (즉시 반영)
                if file_id in PROCESSING_STATUS:
                    del PROCESSING_STATUS[file_id]
                    print(f"🧹 메모리 상태 제거 완료 (DB 커밋 직후): {file_id}")

                # DetectedName 개수 확인
                detected_name_count = db.query(DetectedName).filter(
                    DetectedName.audio_file_id == audio_file_id_db
                ).count()
                speaker_mapping_count = db.query(SpeakerMapping).filter(
                    SpeakerMapping.audio_file_id == audio_file_id_db
                ).count()
                print(f"  - DetectedName 레코드: {detected_name_count}개")
                print(f"  - STTResult 레코드: {len(merged_result) if merged_result else 0}개")
                print(f"  - DiarizationResult 레코드: {len(diarization_result.get('turns', [])) if diarization_result else 0}개")
                print(f"  - SpeakerMapping 레코드: {speaker_mapping_count}개")
                print(f"  - KeyTerm 레코드: {len(extracted_keywords)}개")
                
                # 6-8) 효율성 분석 트리거 (비동기)
                # 재분석 시 효율성 지표도 갱신되어야 함
                print(f"📊 효율성 분석 트리거: audio_file_id={audio_file_id_db}")
                from app.api.v1.efficiency import run_efficiency_analysis
                
                # 현재 스레드에서 바로 실행하지 않고, 별도 스레드/프로세스로 실행하거나
                # 여기서는 간단히 함수 호출 (run_efficiency_analysis 내부에서 새 DB 세션 생성함)
                # 주의: 이미 백그라운드 태스크 내부이므로, 동기적으로 호출해도 무방하나
                # 시간이 걸릴 수 있으므로 별도 스레드로 실행하는 것이 좋음
                
                # 여기서는 간단히 동기 호출 (어차피 백그라운드 태스크임)
                try:
                    run_efficiency_analysis(str(audio_file_id_db))
                except Exception as eff_error:
                    print(f"⚠️ 효율성 분석 실패 (무시함): {eff_error}")

                # 6-9) 화자 태깅 에이전트 자동 실행 (재분석의 경우)
                # 화자 수가 변경되어 재분석된 경우, 에이전트도 다시 실행해야 함
                print(f"🤖 화자 태깅 에이전트 트리거: audio_file_id={audio_file_id_db}")
                from app.api.v1.tagging import run_tagging_agent
                import asyncio
                
                try:
                    # run_tagging_agent는 async 함수이므로 동기 함수인 process_audio_pipeline에서 실행하려면 이벤트 루프 필요
                    # 이미 다른 루프가 돌고 있을 수 있으므로 체크
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    if loop.is_running():
                        # 이미 루프가 실행 중이면 (드문 경우) create_task 사용 불가 (동기 함수라)
                        # 별도 스레드에서 실행
                        import threading
                        def run_async_in_thread():
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            new_loop.run_until_complete(run_tagging_agent(str(file_id), audio_file_id_db, audio_file.user_id))
                            new_loop.close()
                        
                        agent_thread = threading.Thread(target=run_async_in_thread)
                        agent_thread.start()
                        agent_thread.join(timeout=300) # 5분 대기
                    else:
                        loop.run_until_complete(run_tagging_agent(str(file_id), audio_file_id_db, audio_file.user_id))
                        
                except Exception as agent_error:
                    print(f"⚠️ 화자 태깅 에이전트 실행 실패 (무시함): {agent_error}")

            except Exception as db_error:
                print(f"⚠️ DB 저장 실패: {db_error}")
                db.rollback()
                # DB 저장 실패해도 파일 결과는 유지

        # 완료
        # 닉네임 목록 추출
        detected_nicknames_list = []
        if nickname_result:
            detected_nicknames_list = [info.get('nickname') for info in nickname_result.values() if info.get('nickname')]
        
        # 완료 시 메모리에서 제거하여 DB 조회를 유도
        if file_id in PROCESSING_STATUS:
            del PROCESSING_STATUS[file_id]
            print(f"🧹 메모리 상태 제거 완료: {file_id}")

    except Exception as e:
        # 에러 발생 시 DB 업데이트
        if 'audio_file' in locals() and audio_file:
            audio_file.status = FileStatus.FAILED
            audio_file.processing_step = "failed"
            audio_file.processing_progress = 0
            audio_file.processing_message = "오류 발생"
            audio_file.error_message = str(e)
            db.commit()

        PROCESSING_STATUS[file_id] = {
            "status": "failed",
            "step": "오류 발생",
            "progress": 0,
            "error": str(e),
        }
        raise  # 에러를 다시 발생시켜 로그에 남김
    finally:
        # DB 세션 종료
        db.close()


@router.post("/process/{file_id}")
async def start_processing(
    file_id: str,
    background_tasks: BackgroundTasks,
    whisper_mode: str = None,  # "local" or "api" (None일 경우 설정값 사용)
    diarization_mode: str = None,  # "senko" or "nemo" (None일 경우 설정값 사용)
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """
    오디오 처리 시작 (백그라운드)

    Args:
        file_id: 업로드된 파일 ID (UUID 또는 DB ID)
        whisper_mode: Whisper 모드 ("local" 또는 "api", 기본값: 설정값)
        diarization_mode: 화자 분리 모델 ("senko" 또는 "nemo", 기본값: 설정값)

    Returns:
        처리 시작 확인 메시지

    Note:
        - model_size: large-v3 고정
        - device: 자동 감지 (CUDA > MPS > CPU)
        - senko: 빠름, 간단
        - nemo: 정확, 세밀한 설정
    """
    import re

    # 파일 존재 확인
    upload_dir = Path("/app/uploads")
    actual_file_id = file_id

    # 숫자 ID인 경우 DB에서 UUID 추출
    if file_id.isdigit():
        audio_file = db.query(AudioFile).filter(AudioFile.id == int(file_id)).first()
        if audio_file and audio_file.file_path:
            match = re.search(r'([a-f0-9\-]{36})', audio_file.file_path)
            if match:
                actual_file_id = match.group(1)

    input_files = list(upload_dir.glob(f"{actual_file_id}.*"))
    if not input_files:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    # 설정값 또는 파라미터 사용
    use_whisper_mode = whisper_mode if whisper_mode else settings.WHISPER_MODE
    use_diarization_mode = diarization_mode if diarization_mode else settings.DIARIZATION_MODE

    # Whisper 모드 검증
    if use_whisper_mode not in ["local", "api"]:
        raise HTTPException(status_code=400, detail="whisper_mode는 'local' 또는 'api'여야 합니다.")

    # Diarization 모드 검증
    if use_diarization_mode not in ["senko", "nemo"]:
        raise HTTPException(status_code=400, detail="diarization_mode는 'senko' 또는 'nemo'여야 합니다.")

    # API 모드일 때 API 키 확인
    if use_whisper_mode == "api" and not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=400, detail="OpenAI API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")

    # 중복 처리 방지: 이미 처리 중인 파일인지 확인
    if actual_file_id in PROCESSING_STATUS:
        current_status = PROCESSING_STATUS[actual_file_id].get("status")
        if current_status not in ["completed", "failed"]:
            # 이미 처리 중이면 현재 상태 반환
            return {
                "file_id": actual_file_id,
                "message": "이미 처리 중입니다.",
                "status": PROCESSING_STATUS[actual_file_id]
            }

    # 디바이스 자동 감지
    detected_device = get_device()

    # 백그라운드 작업 시작
    PROCESSING_STATUS[actual_file_id] = {
        "status": "queued",
        "step": "대기 중...",
        "progress": 0,
        "whisper_mode": use_whisper_mode,
        "diarization_mode": use_diarization_mode,
        "model_size": "large-v3",
        "device": detected_device,
    }

    # 백그라운드 태스크 시작 (내부에서 DB 세션 생성)
    background_tasks.add_task(
        process_audio_pipeline,
        actual_file_id,
        current_user.id,
        use_whisper_mode,
        use_diarization_mode
    )

    return {
        "file_id": actual_file_id,
        "message": "처리가 시작되었습니다.",
        "status": "queued",
        "whisper_mode": use_whisper_mode,
        "diarization_mode": use_diarization_mode,
        "model_size": "large-v3",
        "device": detected_device,
    }


@router.get("/status/{file_id}")
async def get_processing_status(file_id: str, db: Session = Depends(get_db)):
    """
    처리 상태 조회 (메모리 또는 DB)

    Args:
        file_id: 파일 ID (UUID 또는 DB ID)

    Returns:
        현재 처리 상태
    """
    import re

    actual_file_id = file_id

    # 숫자 ID인 경우 DB에서 UUID 추출
    if file_id.isdigit():
        audio_file = db.query(AudioFile).filter(AudioFile.id == int(file_id)).first()
        if audio_file and audio_file.file_path:
            match = re.search(r'([a-f0-9\-]{36})', audio_file.file_path)
            if match:
                actual_file_id = match.group(1)

    # 메모리에 있으면 반환 (처리 중인 파일)
    if actual_file_id in PROCESSING_STATUS:
        status = PROCESSING_STATUS[actual_file_id]
        # 메모리에 닉네임이 없으면 DB에서 가져오기
        if status.get("status") == "completed" and "detected_nicknames" not in status:
            audio_file = None
            if file_id.isdigit():
                audio_file = db.query(AudioFile).filter(AudioFile.id == int(file_id)).first()
            if not audio_file:
                audio_file = db.query(AudioFile).filter(
                    (AudioFile.file_path.like(f"%{file_id}%")) |
                    (AudioFile.original_filename.like(f"%{file_id}%"))
                ).first()
            if audio_file:
                speaker_mappings = db.query(SpeakerMapping).filter(
                    SpeakerMapping.audio_file_id == audio_file.id
                ).all()
                detected_nicknames = [mapping.nickname for mapping in speaker_mappings if mapping.nickname]
                status["detected_nicknames"] = detected_nicknames
        print(f"[DEBUG] Memory Status for {actual_file_id}: {status.get('status')} (Step: {status.get('step')})")
        return status

    # DB에서 조회 (완료된 파일) - ID(숫자)로 먼저 시도
    audio_file = None
    if file_id.isdigit():
        audio_file = db.query(AudioFile).filter(AudioFile.id == int(file_id)).first()
    if not audio_file:
        audio_file = db.query(AudioFile).filter(
            (AudioFile.file_path.like(f"%{file_id}%")) |
            (AudioFile.original_filename.like(f"%{file_id}%"))
        ).first()

    if not audio_file:
        raise HTTPException(status_code=404, detail="처리 정보를 찾을 수 없습니다.")

    # 화자 수 조회
    speaker_count = db.query(func.count(SpeakerMapping.id)).filter(
        SpeakerMapping.audio_file_id == audio_file.id
    ).scalar() or 0

    # 감지된 이름 조회 (중복 제거)
    detected_names_query = db.query(DetectedName.detected_name).filter(
        DetectedName.audio_file_id == audio_file.id
    ).distinct().all()
    detected_names = [name[0] for name in detected_names_query]

    # 닉네임 조회 (화자별 닉네임)
    speaker_mappings = db.query(SpeakerMapping).filter(
        SpeakerMapping.audio_file_id == audio_file.id
    ).all()
    detected_nicknames = []
    for mapping in speaker_mappings:
        if mapping.nickname:
            detected_nicknames.append(mapping.nickname)

    # 완료된 파일의 상태 반환
    print(f"[DEBUG] DB Status for {file_id}: {audio_file.status.value}")
    return {
        "status": audio_file.status.value if audio_file.status else "unknown",
        "step": "완료" if audio_file.status.value == "completed" else "처리 중",
        "progress": 100 if audio_file.status.value == "completed" else 0,
        "speaker_count": speaker_count,
        "detected_names": detected_names,
        "detected_nicknames": detected_nicknames,  # 닉네임 추가
    }


@router.get("/transcript/{file_id}")
async def get_transcript(file_id: str):
    """
    전사 결과 조회

    Args:
        file_id: 파일 ID

    Returns:
        전사 텍스트
    """
    if file_id not in PROCESSING_STATUS:
        raise HTTPException(status_code=404, detail="처리 정보를 찾을 수 없습니다.")

    status = PROCESSING_STATUS[file_id]
    if status["status"] != "completed":
        raise HTTPException(status_code=400, detail="처리가 완료되지 않았습니다.")

    transcript_path = Path(status["transcript_path"])
    if not transcript_path.exists():
        raise HTTPException(status_code=404, detail="전사 파일을 찾을 수 없습니다.")

    lines = []
    for line in transcript_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            lines.append(line)

    return {"file_id": file_id, "transcript": lines, "total_lines": len(lines)}


@router.get("/ner/{file_id}")
async def get_ner_result(file_id: str):
    """
    NER 결과 조회

    Args:
        file_id: 파일 ID

    Returns:
        NER 처리 결과 (이름 목록, 군집화 정보, 통계 등)
    """
    if file_id not in PROCESSING_STATUS:
        raise HTTPException(status_code=404, detail="처리 정보를 찾을 수 없습니다.")

    status = PROCESSING_STATUS[file_id]
    if status["status"] != "completed":
        raise HTTPException(status_code=400, detail="처리가 완료되지 않았습니다.")

    ner_path = status.get("ner_path")
    if not ner_path or not Path(ner_path).exists():
        raise HTTPException(status_code=404, detail="NER 결과 파일을 찾을 수 없습니다.")

    # NER 결과 로드
    with open(ner_path, 'r', encoding='utf-8') as f:
        ner_result = json.load(f)

    return {
        "file_id": file_id,
        "detected_names": ner_result.get("final_namelist", []),
        "name_clusters": ner_result.get("name_clusters", {}),
        "unique_names": ner_result.get("unique_names", []),
        "stats": ner_result.get("stats", {}),
        "segments_with_names": ner_result.get("segments_with_names", []),
    }


@router.get("/files")
async def get_processed_files(db: Session = Depends(get_db)):
    """
    처리된 파일 목록 조회

    Returns:
        처리된 파일들의 목록 (최근순)
    """
    files = db.query(AudioFile).order_by(AudioFile.created_at.desc()).limit(20).all()

    result = []
    for f in files:
        # 각 파일의 통계 정보
        stt_count = db.query(func.count(STTResult.id)).filter(
            STTResult.audio_file_id == f.id
        ).scalar() or 0

        diar_count = db.query(func.count(DiarizationResult.id)).filter(
            DiarizationResult.audio_file_id == f.id
        ).scalar() or 0

        name_count = db.query(func.count(DetectedName.id)).filter(
            DetectedName.audio_file_id == f.id
        ).scalar() or 0

        # file_path에서 file_id 추출 (UUID 부분)
        file_id = Path(f.file_path).stem if f.file_path else f"file_{f.id}"

        result.append({
            "id": f.id,
            "file_id": file_id,
            "filename": f.original_filename,
            "status": f.status.value if f.status else "unknown",
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "duration": f.duration,
            "stt_segments": stt_count,
            "diarization_segments": diar_count,
            "detected_names": name_count
        })

    return {"files": result, "total": len(result)}


@router.get("/merged/{file_id}")
async def get_merged_result(file_id: str, db: Session = Depends(get_db)):
    """
    병합된 결과 조회 (STT + Diarization + NER) - DB 우선, 메모리 폴백

    Args:
        file_id: 파일 ID

    Returns:
        화자 정보와 이름이 포함된 전사 결과
    """
    # 1. DB에서 조회 시도
    audio_file = db.query(AudioFile).filter(
        (AudioFile.file_path.like(f"%{file_id}%")) |
        (AudioFile.original_filename.like(f"%{file_id}%"))
    ).first()

    if audio_file:
        # STT 결과 조회 (시간순 정렬)
        stt_results = db.query(STTResult).filter(
            STTResult.audio_file_id == audio_file.id
        ).order_by(STTResult.start_time).all()

        # Diarization 결과를 딕셔너리로 변환 (시간대별 화자 매핑)
        diar_results = db.query(DiarizationResult).filter(
            DiarizationResult.audio_file_id == audio_file.id
        ).order_by(DiarizationResult.start_time).all()

        # STT와 Diarization 병합
        merged_segments = []
        for stt in stt_results:
            # 해당 STT 시간대에 겹치는 화자 찾기
            speaker_label = "UNKNOWN"
            for diar in diar_results:
                # STT 시작 시간이 화자 구간 안에 있으면
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

        # 화자 수 조회
        speaker_count = db.query(func.count(SpeakerMapping.id.distinct())).filter(
            SpeakerMapping.audio_file_id == audio_file.id
        ).scalar() or 0

        return {
            "file_id": file_id,
            "segments": merged_segments,
            "total_segments": len(merged_segments),
            "detected_names": detected_names_list,
            "speaker_count": speaker_count,
        }

    # 2. 메모리에서 조회 (폴백)
    if file_id not in PROCESSING_STATUS:
        raise HTTPException(status_code=404, detail="처리 정보를 찾을 수 없습니다.")

    status = PROCESSING_STATUS[file_id]
    if status["status"] != "completed":
        raise HTTPException(status_code=400, detail="처리가 완료되지 않았습니다.")

    # NER 결과 로드
    ner_path = status.get("ner_path")
    if ner_path and Path(ner_path).exists():
        with open(ner_path, 'r', encoding='utf-8') as f:
            ner_result = json.load(f)
        segments = ner_result.get("segments_with_names", [])
    else:
        # NER 없으면 병합 결과만
        merged_path = status.get("merged_path")
        if not merged_path or not Path(merged_path).exists():
            raise HTTPException(status_code=404, detail="병합 결과를 찾을 수 없습니다.")

        with open(merged_path, 'r', encoding='utf-8') as f:
            segments = json.load(f)

    return {
        "file_id": file_id,
        "segments": segments,
        "total_segments": len(segments),
        "detected_names": status.get("detected_names", []),
        "speaker_count": status.get("speaker_count", 0),
    }


@router.get("/export/{file_id}")
async def export_merged_json(file_id: str, db: Session = Depends(get_db)):
    """
    병합된 결과를 JSON 파일로 내보내기

    Args:
        file_id: 파일 ID

    Returns:
        저장된 JSON 파일 경로
    """
    # get_merged_result와 동일한 로직으로 데이터 조회
    audio_file = db.query(AudioFile).filter(
        (AudioFile.file_path.like(f"%{file_id}%")) |
        (AudioFile.original_filename.like(f"%{file_id}%"))
    ).first()

    if not audio_file:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    # STT 결과 조회
    stt_results = db.query(STTResult).filter(
        STTResult.audio_file_id == audio_file.id
    ).order_by(STTResult.start_time).all()

    # Diarization 결과 조회
    diar_results = db.query(DiarizationResult).filter(
        DiarizationResult.audio_file_id == audio_file.id
    ).order_by(DiarizationResult.start_time).all()

    # 화자별 임베딩 수집 (각 화자의 첫 번째 레코드에서 가져오기)
    speaker_embeddings = {}
    for diar in diar_results:
        if diar.speaker_label not in speaker_embeddings and diar.embedding:
            speaker_embeddings[diar.speaker_label] = diar.embedding

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
    export_dir = Path("/app/uploads/exports")
    export_dir.mkdir(exist_ok=True, parents=True)

    export_filename = f"{file_id}_merged.json"
    export_path = export_dir / export_filename

    with open(export_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)

    return {
        "message": "JSON 파일 생성 완료",
        "file_path": str(export_path),
        "file_name": export_filename,
        "total_segments": len(merged_segments),
    }


@router.get("/status/{file_id}")
async def get_processing_status(
    file_id: int,
    db: Session = Depends(get_db)
):
    """
    파일 처리 진행 상태 조회 (대시보드용)

    Args:
        file_id: 오디오 파일 ID

    Returns:
        처리 상태 정보
    """
    audio_file = db.query(AudioFile).filter(AudioFile.id == file_id).first()

    if not audio_file:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    return {
        "file_id": file_id,
        "filename": audio_file.original_filename,
        "status": audio_file.status.value,
        "processing_step": audio_file.processing_step,
        "progress": audio_file.processing_progress,
        "message": audio_file.processing_message,
        "error": audio_file.error_message,
        "duration": audio_file.duration,
        "created_at": audio_file.created_at,
        "updated_at": audio_file.updated_at
    }
