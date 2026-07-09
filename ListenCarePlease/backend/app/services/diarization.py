"""
화자 분리 서비스 (I,O.md Step 4)
- 모델 1: Senko (빠름, 간단)
- 모델 2: NeMo (정확, 세밀한 설정)
- 화자별 임베딩 추출
"""
import app.patch_torch  # Apply monkey patch first
from pathlib import Path
from typing import Dict, List
import numpy as np

try:
    import senko
    SENKO_AVAILABLE = True
except ImportError:
    SENKO_AVAILABLE = False
    print("⚠️ Senko not installed. Install with: pip install git+https://github.com/narcotic-sh/senko.git")

from app.core.device import get_device


def run_diarization(audio_path: Path, device: str = None, mode: str = "senko", num_speakers: int = None) -> Dict:
    """
    화자 분리 통합 인터페이스

    Args:
        audio_path: 오디오 파일 경로
        device: 디바이스 ("cuda", "cpu", None=auto)
        mode: 화자 분리 모델 ("senko" or "nemo")

    Returns:
        화자 분리 결과 (turns + embeddings)
    """
    if mode == "nemo":
        # NeMo 모델 사용
        from app.services.diarization_nemo import run_diarization_nemo
        return run_diarization_nemo(audio_path, device, num_speakers=num_speakers)
    else:
        # Senko 모델 사용 (기본값)
        return run_diarization_senko(audio_path, device)


def run_diarization_senko(audio_path: Path, device: str = None) -> Dict:
    """
    Senko를 사용한 화자 분리

    Args:
        audio_path: 오디오 파일 경로 (전처리된 WAV)
        device: 디바이스 ("cuda", "mps", "cpu", None=auto)

    Returns:
        {
            "turns": [
                {"speaker_label": "speaker_00", "start": 0.0, "end": 5.2},
                ...
            ],
            "embeddings": {
                "speaker_00": [0.1, 0.2, ...],  # 192차원 벡터
                ...
            }
        }
    """
    import torch

    if not SENKO_AVAILABLE:
        raise ImportError("Senko is not installed. Please install it first.")

    # 디바이스 자동 감지
    if device is None:
        device = get_device()

    # CUDA 실제 사용 가능 여부 재확인 (Docker와 실제 환경 불일치 방지)
    if device == "cuda" and not torch.cuda.is_available():
        print("⚠️ CUDA requested but not available. Falling back to CPU.")
        device = "cpu"

    # Senko는 'auto' 또는 'cpu'/'cuda' 지원
    # MPS는 지원하지 않으므로 CPU로 폴백
    if device == "mps":
        print("⚠️ Senko does not support MPS. Using CPU instead.")
        device = "cpu"

    print(f"[Diarization] Using device: {device}")
    print(f"[Diarization] Processing: {audio_path}")

    # 메모리 정리 (Diarization 시작 전)
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # Senko Diarizer 초기화 (warmup은 메모리를 많이 사용하므로 CPU에서는 비활성화)
    warmup = device != "cpu"  # CPU에서는 warmup 비활성화로 메모리 절약
    print(f"[Diarization] Warmup: {warmup}")
    diarizer = senko.Diarizer(device=device, warmup=warmup, quiet=False)

    # 화자 분리 실행
    senko_result = diarizer.diarize(str(audio_path), generate_colors=False)

    # 결과 변환
    result = convert_senko_to_custom_format(senko_result)

    # Diarization 완료 후 메모리 정리
    del diarizer
    del senko_result
    gc.collect()

    print(f"[Diarization] Detected {len(result['embeddings'])} speakers")
    print(f"[Diarization] {len(result['turns'])} segments")

    return result


def convert_senko_to_custom_format(senko_result: Dict) -> Dict:
    """
    Senko 결과를 우리 프로젝트 형식으로 변환

    Args:
        senko_result: Senko diarizer 결과
            - merged_segments: List[Dict] - 화자별 시간 구간
            - speaker_centroids: Dict[str, np.ndarray] - 화자별 임베딩

    Returns:
        {
            "turns": [{"speaker_label": str, "start": float, "end": float}],
            "embeddings": {speaker_label: List[float]}
        }
    """
    # 1. turns 데이터 생성
    turns = []
    for segment in senko_result['merged_segments']:
        turns.append({
            "speaker_label": segment['speaker'],
            "start": round(segment['start'], 2),
            "end": round(segment['end'], 2)
        })

    # 2. embeddings 데이터 생성
    embeddings = {}
    for speaker, centroid in senko_result['speaker_centroids'].items():
        # numpy array를 list로 변환
        if isinstance(centroid, np.ndarray):
            embeddings[speaker] = centroid.tolist()
        else:
            embeddings[speaker] = list(centroid)

    result = {
        "turns": turns,
        "embeddings": embeddings
    }

    return result


def merge_stt_with_diarization(
    stt_segments: List[Dict], diarization_result: Dict
) -> List[Dict]:
    """
    STT 결과와 화자 분리 결과 병합

    Args:
        stt_segments: STT 결과
            [{"text": str, "start": float, "end": float}, ...]
        diarization_result: 화자 분리 결과
            {"turns": [...], "embeddings": {...}}

    Returns:
        [
            {
                "speaker": "speaker_00",
                "start": 0.0,
                "end": 5.2,
                "text": "안녕하세요"
            },
            ...
        ]
    """
    merged = []
    stt_idx = 0

    for turn in diarization_result['turns']:
        speaker = turn['speaker_label']
        start_turn = turn['start']
        end_turn = turn['end']

        segment_text = ""

        # STT 세그먼트 탐색
        while stt_idx < len(stt_segments):
            stt = stt_segments[stt_idx]
            start_stt = stt['start']
            end_stt = stt['end']

            # STT 세그먼트가 현재 화자 구간 내에 있는 경우
            if start_stt >= start_turn and start_stt < end_turn:
                segment_text += stt['text'].strip() + " "
                stt_idx += 1
            elif start_stt >= end_turn:
                # 다음 화자 구간으로 이동
                break
            else:
                stt_idx += 1

        # 텍스트가 있는 경우만 추가
        if segment_text.strip():
            merged.append({
                "speaker": speaker,
                "start": start_turn,
                "end": end_turn,
                "text": segment_text.strip()
            })

    return merged
