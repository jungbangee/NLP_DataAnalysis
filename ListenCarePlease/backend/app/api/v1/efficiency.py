"""
회의 효율성 분석 API 엔드포인트
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user
from app.models.efficiency import MeetingEfficiencyAnalysis
from app.models.audio_file import AudioFile
from app.services.efficiency_analyzer import EfficiencyAnalyzer
from typing import List, Optional
import logging
import os
from openai import OpenAI
from langsmith import traceable

logger = logging.getLogger(__name__)

# 파일 로깅 설정
try:
    log_dir = "/app/uploads"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    file_handler = logging.FileHandler(os.path.join(log_dir, "efficiency_analysis.log"))
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except Exception as e:
    print(f"Failed to setup file logging: {e}")

router = APIRouter()

# OpenAI 클라이언트 초기화
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@traceable(name="generate_efficiency_insight", run_type="llm")
def generate_insight(metric_name: str, values: List[float], avg: float, std: float = None) -> str:
    """
    LLM을 사용하여 지표에 대한 한줄 평 생성

    Args:
        metric_name: 지표 이름 (예: "엔트로피", "TTR", "PPL")
        values: 시계열 값 리스트
        avg: 평균값
        std: 표준편차 (선택)

    Returns:
        한줄 평 문자열
    """
    try:
        # 간단한 통계 계산
        if len(values) > 0:
            # values가 숫자 리스트인지 확인
            numeric_values = []
            for v in values:
                if isinstance(v, (int, float)):
                    numeric_values.append(v)
                elif isinstance(v, dict):
                    # dict인 경우 건너뛰기 (비교 불가)
                    continue

            # 숫자 값이 있을 때만 추세 계산
            if len(numeric_values) >= 2:
                trend = "상승" if numeric_values[-1] > numeric_values[0] else "하락" if numeric_values[-1] < numeric_values[0] else "안정"
            else:
                trend = "안정"

            volatility = "높음" if std and std > avg * 0.3 else "낮음"
        else:
            return f"{metric_name} 데이터가 부족합니다."

        prompt = f"""회의 효율성 지표에 대한 간단한 한줄 평을 작성해주세요.

지표명: {metric_name}
평균: {avg:.3f}
추세: {trend}
변동성: {volatility}
데이터 포인트 수: {len(values)}

한줄로 회의의 특징을 설명해주세요. 예: "회의 내내 일관된 주제로 집중된 논의가 진행되었습니다." 또는 "초반 활발했다가 후반부로 갈수록 집중도가 떨어졌습니다."
"""

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 회의 분석 전문가입니다. 주어진 지표를 바탕으로 회의의 특징을 한문장으로 요약합니다."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.7
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"Failed to generate insight: {e}")
        return f"{metric_name} 분석이 완료되었습니다."


# 전역 변수로 분석 중인 파일 추적 (간단한 인메모리 락)
processing_files = set()

def run_efficiency_analysis(audio_file_id: str):
    """백그라운드 작업: 효율성 분석 실행"""
    print(f"[DEBUG] run_efficiency_analysis called with audio_file_id={audio_file_id}", flush=True)
    
    # 백그라운드 태스크에서는 새로운 DB 세션 생성 필요
    from app.db.base import SessionLocal

    db = SessionLocal()
    try:
        logger.info(f"Background task started: efficiency analysis for audio_file_id={audio_file_id}")

        # 분석 실행
        print(f"[DEBUG] Initializing EfficiencyAnalyzer for audio_file_id={audio_file_id}", flush=True)
        analyzer = EfficiencyAnalyzer(audio_file_id, db)
        print(f"[DEBUG] Starting analyze_all()", flush=True)
        analysis = analyzer.analyze_all()
        print(f"[DEBUG] analyze_all() completed. Result: {analysis}", flush=True)

        # === 인사이트 생성 (한 번만!) ===
        try:
            # 엔트로피 인사이트
            entropy_values = [v['entropy'] for v in analysis.entropy_values] if analysis.entropy_values else []
            entropy_insight = generate_insight(
                "엔트로피",
                entropy_values,
                analysis.entropy_avg,
                analysis.entropy_std
            )
        except Exception as e:
            logger.error(f"Failed to generate entropy insight: {e}")
            entropy_insight = "분석 중 오류가 발생했습니다."

        # 전체 회의 지표 인사이트
        overall_ttr_insight = None
        if analysis.overall_ttr:
            ttr_vals = analysis.overall_ttr.get('ttr_values', [])
            overall_ttr_insight = generate_insight(
                "전체 회의 TTR",
                ttr_vals,
                analysis.overall_ttr.get('ttr_avg', 0),
                analysis.overall_ttr.get('ttr_std', 0)
            )

        overall_info_insight = None
        if analysis.overall_information_content:
            info_score = analysis.overall_information_content.get('information_score', 0)
            overall_info_insight = generate_insight(
                "전체 회의 정보량",
                [info_score] * 10,
                info_score,
                0
            )

        overall_sentence_prob_insight = None
        if analysis.overall_sentence_probability:
            outlier_ratio = analysis.overall_sentence_probability.get('outlier_ratio', 0)
            avg_prob = analysis.overall_sentence_probability.get('avg_probability', 0)

            if outlier_ratio >= 0.99:
                overall_sentence_prob_insight = "영상의 길이가 짧아 통계적으로 유의미한 분석이 어렵습니다."
            else:
                overall_sentence_prob_insight = generate_insight(
                    "전체 회의 문장 확률",
                    [avg_prob, outlier_ratio],
                    avg_prob,
                    0
                )

        overall_ppl_insight = None
        if analysis.overall_perplexity:
            # overall_perplexity['ppl_values'] is a list of scalars (floats), not dicts
            ppl_vals = analysis.overall_perplexity.get('ppl_values', [])
            # Ensure they are standard floats
            ppl_vals = [float(v) for v in ppl_vals]
            
            overall_ppl_insight = generate_insight(
                "전체 회의 PPL",
                ppl_vals,
                analysis.overall_perplexity.get('ppl_avg', 0),
                analysis.overall_perplexity.get('ppl_std', 0)
            )

        # 화자별 인사이트 생성 및 speaker_metrics에 추가
        updated_speaker_metrics = []
        for speaker in analysis.speaker_metrics:
            speaker_data = speaker.copy()

            # TTR 인사이트
            if speaker.get('ttr') and speaker['ttr'].get('ttr_values'):
                ttr_insight = generate_insight(
                    f"{speaker.get('speaker_name', 'Unknown')}의 TTR",
                    speaker['ttr']['ttr_values'],
                    speaker['ttr']['ttr_avg'],
                    speaker['ttr'].get('ttr_std')
                )
                speaker_data['ttr']['insight'] = ttr_insight

            # 정보량 인사이트
            if speaker.get('information_content'):
                info_score = speaker['information_content'].get('information_score', 0)
                info_insight = generate_insight(
                    f"{speaker.get('speaker_name', 'Unknown')}의 정보량",
                    [info_score] * 10,
                    info_score,
                    0
                )
                speaker_data['information_content']['insight'] = info_insight

            # 문장 확률 인사이트
            if speaker.get('sentence_probability'):
                outlier_ratio = speaker['sentence_probability'].get('outlier_ratio', 0)
                avg_prob = speaker['sentence_probability'].get('avg_probability', 0)

                if outlier_ratio >= 0.99:
                    sentence_insight = "영상의 길이가 짧아 통계적으로 유의미한 분석이 어렵습니다."
                else:
                    sentence_insight = generate_insight(
                        f"{speaker.get('speaker_name', 'Unknown')}의 문장 확률",
                        [avg_prob, outlier_ratio],
                        avg_prob,
                        0
                    )
                speaker_data['sentence_probability']['insight'] = sentence_insight

            # PPL 인사이트
            if speaker.get('perplexity') and speaker['perplexity'].get('ppl_values'):
                ppl_vals = [v['ppl'] for v in speaker['perplexity']['ppl_values']]
                ppl_insight = generate_insight(
                    f"{speaker.get('speaker_name', 'Unknown')}의 PPL",
                    ppl_vals,
                    speaker['perplexity']['ppl_avg'],
                    speaker['perplexity'].get('ppl_std')
                )
                speaker_data['perplexity']['insight'] = ppl_insight

            updated_speaker_metrics.append(speaker_data)

        # 계산된 인사이트를 analysis 객체에 할당
        analysis.entropy_insight = entropy_insight
        analysis.overall_ttr_insight = overall_ttr_insight
        analysis.overall_info_insight = overall_info_insight
        analysis.overall_sentence_prob_insight = overall_sentence_prob_insight
        analysis.overall_ppl_insight = overall_ppl_insight
        analysis.speaker_metrics = updated_speaker_metrics

        print(f"[DEBUG] Insights assigned to analysis object", flush=True)

        # DB 업데이트/생성 로직 함수화
        def update_analysis_fields(target, source):
            target.entropy_values = source.entropy_values
            target.entropy_avg = source.entropy_avg
            target.entropy_std = source.entropy_std
            target.overall_ttr = source.overall_ttr
            target.overall_information_content = source.overall_information_content
            target.overall_sentence_probability = source.overall_sentence_probability
            target.overall_perplexity = source.overall_perplexity
            target.speaker_metrics = source.speaker_metrics
            target.total_speakers = source.total_speakers
            target.total_turns = source.total_turns
            target.total_sentences = source.total_sentences
            target.analysis_version = "1.0"
            target.analyzed_at = datetime.now(timezone.utc)
            target.entropy_insight = source.entropy_insight
            target.overall_ttr_insight = source.overall_ttr_insight
            target.overall_info_insight = source.overall_info_insight
            target.overall_sentence_prob_insight = source.overall_sentence_prob_insight
            target.overall_ppl_insight = source.overall_ppl_insight
            target.qualitative_analysis = source.qualitative_analysis
            target.silence_analysis = source.silence_analysis
            target.interaction_analysis = source.interaction_analysis

        from sqlalchemy.exc import IntegrityError
        from datetime import datetime, timezone

        # 기존 분석 결과가 있으면 업데이트, 없으면 새로 생성
        existing = db.query(MeetingEfficiencyAnalysis).filter(
            MeetingEfficiencyAnalysis.audio_file_id == audio_file_id
        ).first()

        if existing:
            logger.info(f"Updating existing analysis for audio_file_id={audio_file_id}")
            print(f"[DEBUG] Updating existing analysis for ID {audio_file_id}", flush=True)
            update_analysis_fields(existing, analysis)
            db.commit()
            db.refresh(existing)
            logger.info(f"Efficiency analysis updated for audio_file_id={audio_file_id}")
            print(f"[DEBUG] DB Commit successful (update)", flush=True)
        else:
            logger.info(f"Creating new analysis for audio_file_id={audio_file_id}")
            print(f"[DEBUG] Creating new analysis for ID {audio_file_id}", flush=True)
            
            try:
                # analysis.audio_file_id가 올바른지 확인
                analysis.audio_file_id = int(audio_file_id) # 강제로 int 변환
                db.add(analysis)
                db.commit()
                db.refresh(analysis)
                logger.info(f"Efficiency analysis created for audio_file_id={audio_file_id}")
                print(f"[DEBUG] DB Commit successful (create). ID: {analysis.id}", flush=True)
            except IntegrityError:
                logger.warning(f"Race condition detected for audio_file_id={audio_file_id}. Switching to update.")
                print(f"[DEBUG] Race condition detected. Switching to update.", flush=True)
                db.rollback()
                
                # 다시 조회 후 업데이트
                existing = db.query(MeetingEfficiencyAnalysis).filter(
                    MeetingEfficiencyAnalysis.audio_file_id == audio_file_id
                ).first()
                
                if existing:
                    update_analysis_fields(existing, analysis)
                    db.commit()
                    db.refresh(existing)
                    print(f"[DEBUG] DB Commit successful (update after race condition)", flush=True)
                else:
                    logger.error("Failed to recover from race condition: record still not found")

    except Exception as e:
        logger.error(f"Error in efficiency analysis background task: {e}", exc_info=True)
        print(f"[DEBUG] Error in background task: {e}", flush=True)
        db.rollback()
    finally:
        db.close()
        # 작업 완료 후 락 해제
        if int(audio_file_id) in processing_files:
            processing_files.remove(int(audio_file_id))
        print(f"[DEBUG] Released lock for audio_file_id={audio_file_id}", flush=True)


@router.post("/analyze/{file_id}", status_code=status.HTTP_202_ACCEPTED)
def trigger_efficiency_analysis(
    file_id: str,
    background_tasks: BackgroundTasks,
    force: bool = False,  # 강제 재분석 플래그
    db: Session = Depends(get_db)
):
    """
    효율성 분석 트리거 (비동기 백그라운드 작업)

    - 기존 분석 결과가 있으면 기존 결과 반환 (force=True면 재분석)
    - BackgroundTasks로 비동기 실행
    - 즉시 202 Accepted 반환
    """
    # AudioFile 찾기 - ID(숫자)로 먼저 시도, 실패시 문자열 검색
    audio_file = None
    if file_id.isdigit():
        audio_file = db.query(AudioFile).filter(AudioFile.id == int(file_id)).first()
    if not audio_file:
        audio_file = db.query(AudioFile).filter(
            (AudioFile.file_path.like(f"%{file_id}%")) |
            (AudioFile.original_filename.like(f"%{file_id}%"))
        ).first()

    if not audio_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audio file {file_id} not found"
        )

    # 이미 분석 중인지 확인 (락)
    if audio_file.id in processing_files:
        print(f"[DEBUG] Analysis already in progress for audio_file_id={audio_file.id}. Skipping.", flush=True)
        return {
            "message": "Efficiency analysis is already in progress",
            "file_id": audio_file.id,
            "status": "processing"
        }

    # 기존 분석 결과 확인
    existing_analysis = db.query(MeetingEfficiencyAnalysis).filter(
        MeetingEfficiencyAnalysis.audio_file_id == audio_file.id
    ).first()

    # 기존 결과가 있고 force=False이면 이미 완료된 것으로 반환
    if existing_analysis and not force:
        return {
            "message": "Efficiency analysis already completed",
            "file_id": audio_file.id,
            "status": "completed",
            "analyzed_at": existing_analysis.analyzed_at.isoformat() if existing_analysis.analyzed_at else None
        }

    # 백그라운드 작업 등록 (DB 세션은 태스크 내부에서 생성)
    # 항상 integer ID 전달
    print(f"[DEBUG] Triggering analysis for audio_file_id={audio_file.id}", flush=True)
    
    # 락 설정
    processing_files.add(audio_file.id)
    background_tasks.add_task(run_efficiency_analysis, audio_file.id)

    return {
        "message": "Efficiency analysis started",
        "file_id": audio_file.id,
        "status": "processing"
    }


@router.get("/overview")
def get_efficiency_overview(
    db: Session = Depends(get_db),
    limit: Optional[int] = 10,
    current_user = Depends(get_current_user)
):
    """
    전체 회의 효율성 조회 (메인 화면 대시보드용)

    - 최근 N개 회의의 효율성 분석 결과 요약
    - 엔트로피 값을 시간 비율(0-100%)로 정규화하여 반환
    """
    analyses = db.query(MeetingEfficiencyAnalysis).join(AudioFile).filter(
        AudioFile.user_id == current_user.id
    ).order_by(
        MeetingEfficiencyAnalysis.analyzed_at.desc()
    ).limit(limit).all()

    results = []
    for analysis in analyses:
        # 엔트로피 값들을 시간 비율(0-100%)로 정규화
        normalized_entropy = []
        if analysis.entropy_values:
            # 최대 시간 값 찾기
            max_time = max(v['time'] for v in analysis.entropy_values) if analysis.entropy_values else 1

            for val in analysis.entropy_values:
                percentage = (val['time'] / max_time) * 100 if max_time > 0 else 0
                normalized_entropy.append({
                    "time_percentage": round(percentage, 1),
                    "entropy": val['entropy']
                })

        results.append({
            "audio_file_id": analysis.audio_file_id,
            "filename": analysis.audio_file.original_filename,
            "entropy_avg": analysis.entropy_avg,
            "entropy_values_normalized": normalized_entropy,
            "total_speakers": analysis.total_speakers,
            "total_turns": analysis.total_turns,
            "analyzed_at": analysis.analyzed_at.isoformat() if analysis.analyzed_at else None
        })

    return {
        "total_count": len(results),
        "analyses": results
    }


@router.get("/{file_id}")
def get_efficiency_analysis(
    file_id: str,
    db: Session = Depends(get_db)
):
    """
    개별 회의 효율성 조회 (결과 페이지용)

    - 분석 결과가 없으면 404 반환
    - 프론트엔드에서 분석 트리거를 먼저 호출해야 함
    """
    # AudioFile 찾기 - ID(숫자)로 먼저 시도, 실패시 문자열 검색
    print(f"[DEBUG] Searching for audio file with ID: {file_id}", flush=True)
    audio_file = None
    if file_id.isdigit():
        audio_file = db.query(AudioFile).filter(AudioFile.id == int(file_id)).first()
    if not audio_file:
        audio_file = db.query(AudioFile).filter(
            (AudioFile.file_path.like(f"%{file_id}%")) |
            (AudioFile.original_filename.like(f"%{file_id}%"))
        ).first()

    if not audio_file:
        print(f"[DEBUG] Audio file NOT found for file_id={file_id}", flush=True)
        # 디버깅을 위해 DB에 있는 파일들 일부 출력
        all_files = db.query(AudioFile).limit(5).all()
        print(f"[DEBUG] Available files (first 5): {[f.file_path for f in all_files]}", flush=True)
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audio file {file_id} not found"
        )

    print(f"[DEBUG] Found audio_file: id={audio_file.id}, path={audio_file.file_path}", flush=True)

    # 분석 결과 조회
    analysis = db.query(MeetingEfficiencyAnalysis).filter(
        MeetingEfficiencyAnalysis.audio_file_id == audio_file.id
    ).first()

    if not analysis:
        print(f"[DEBUG] Efficiency analysis NOT found for audio_file_id={audio_file.id}", flush=True)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Efficiency analysis not found for file {file_id}. Please trigger analysis first."
        )

    # === DB에서 인사이트 조회 (LLM 호출 제거!) ===
    entropy_insight = analysis.entropy_insight or "분석 중입니다."
    overall_ttr_insight = analysis.overall_ttr_insight
    overall_info_insight = analysis.overall_info_insight
    overall_sentence_prob_insight = analysis.overall_sentence_prob_insight
    overall_ppl_insight = analysis.overall_ppl_insight

    # 화자별 인사이트는 이미 speaker_metrics JSON에 포함되어 있음
    speaker_metrics_with_insights = analysis.speaker_metrics

    # 전체 회의 지표에 인사이트 추가
    overall_ttr_data = None
    if analysis.overall_ttr:
        overall_ttr_data = analysis.overall_ttr.copy()
        overall_ttr_data['insight'] = overall_ttr_insight

    overall_info_data = None
    if analysis.overall_information_content:
        overall_info_data = analysis.overall_information_content.copy()
        overall_info_data['insight'] = overall_info_insight

    overall_sentence_prob_data = None
    if analysis.overall_sentence_probability:
        overall_sentence_prob_data = analysis.overall_sentence_probability.copy()
        overall_sentence_prob_data['insight'] = overall_sentence_prob_insight

    overall_ppl_data = None
    if analysis.overall_perplexity:
        overall_ppl_data = analysis.overall_perplexity.copy()
        overall_ppl_data['insight'] = overall_ppl_insight

    return {
        "audio_file_id": analysis.audio_file_id,
        "entropy": {
            "values": analysis.entropy_values,
            "avg": analysis.entropy_avg,
            "std": analysis.entropy_std,
            "insight": entropy_insight
        },
        "overall_ttr": overall_ttr_data,
        "overall_information_content": overall_info_data,
        "overall_sentence_probability": overall_sentence_prob_data,
        "overall_perplexity": overall_ppl_data,
        "speaker_metrics": speaker_metrics_with_insights,
        "total_speakers": analysis.total_speakers,
        "total_turns": analysis.total_turns,
        "total_sentences": analysis.total_sentences,
        "analysis_version": analysis.analysis_version,
        "analyzed_at": analysis.analyzed_at.isoformat() if analysis.analyzed_at else None,
        
        # New fields
        "qualitative_analysis": analysis.qualitative_analysis,
        "silence_analysis": analysis.silence_analysis,
        "interaction_analysis": analysis.interaction_analysis
    }


@router.get("/{file_id}/speaker/{speaker_label}")
def get_speaker_efficiency(
    file_id: str,
    speaker_label: str,
    db: Session = Depends(get_db)
):
    """
    특정 화자의 효율성 지표 조회

    - speaker_metrics에서 해당 화자만 추출
    """
    # AudioFile 찾기
    audio_file = None
    if file_id.isdigit():
        audio_file = db.query(AudioFile).filter(AudioFile.id == int(file_id)).first()
    if not audio_file:
        audio_file = db.query(AudioFile).filter(
            (AudioFile.file_path.like(f"%{file_id}%")) |
            (AudioFile.original_filename.like(f"%{file_id}%"))
        ).first()

    if not audio_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audio file {file_id} not found"
        )

    analysis = db.query(MeetingEfficiencyAnalysis).filter(
        MeetingEfficiencyAnalysis.audio_file_id == audio_file.id
    ).first()

    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Efficiency analysis not found for file {file_id}"
        )

    # speaker_metrics에서 해당 화자 찾기
    speaker_metric = next(
        (m for m in analysis.speaker_metrics if m["speaker_label"] == speaker_label),
        None
    )

    if not speaker_metric:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Speaker {speaker_label} not found in analysis"
        )

    return speaker_metric
