"""
NeMo 기반 화자 분리 서비스
- NVIDIA NeMo Toolkit 사용
- TitaNet 모델 (192차원 임베딩)
- Multi-scale 분석 지원
"""
from pathlib import Path
from typing import Dict, List
import numpy as np
import json
import os

try:
    import torch
    import torchaudio
    from omegaconf import OmegaConf
    from nemo.collections.asr.models.msdd_models import NeuralDiarizer
    from nemo.collections.asr.models import EncDecSpeakerLabelModel
    NEMO_AVAILABLE = True
except ImportError:
    NEMO_AVAILABLE = False
    print("⚠️ NeMo not installed. Install with: pip install nemo-toolkit[asr]")

from app.core.device import get_device


def run_diarization_nemo(audio_path: Path, device: str = None, num_speakers: int = None) -> Dict:
    """
    NeMo를 사용한 화자 분리 (고급 모드)

    Args:
        audio_path: 오디오 파일 경로 (전처리된 WAV)
        device: 디바이스 ("cuda", "cpu", None=auto)

    Returns:
        {
            "turns": [
                {"speaker_label": "SPEAKER_00", "start": 0.0, "end": 5.2},
                ...
            ],
            "embeddings": {
                "SPEAKER_00": [0.1, 0.2, ...],  # 192차원 벡터
                ...
            }
        }
    """
    if not NEMO_AVAILABLE:
        raise ImportError("NeMo is not installed. Please install it first.")

    # 디바이스 자동 감지
    if device is None:
        device = get_device()

    # CUDA 실제 사용 가능 여부 재확인
    if device == "cuda" and not torch.cuda.is_available():
        print("⚠️ CUDA requested but not available. Falling back to CPU.")
        device = "cpu"

    # NeMo는 MPS 미지원
    if device == "mps":
        print("⚠️ NeMo does not support MPS. Using CPU instead.")
        device = "cpu"

    # cuDNN 비활성화 (NeMo 호환성)
    torch.backends.cudnn.enabled = False

    print(f"[Diarization-NeMo] Using device: {device}")
    print(f"[Diarization-NeMo] Processing: {audio_path}")

    # 작업 디렉토리 생성
    work_dir = audio_path.parent / "nemo_work"
    work_dir.mkdir(exist_ok=True)

    # 1. Manifest 파일 생성 (NeMo 입력 형식)
    manifest_path = work_dir / "manifest.json"
    with open(manifest_path, 'w') as f:
        json.dump({
            "audio_filepath": str(audio_path),
            "offset": 0,
            "duration": None,
            "label": "infer",
            "text": "-",
            "num_speakers": num_speakers,
            "rttm_filepath": None,
            "uem_filepath": None
        }, f)
        f.write('\n')

    # 2. NeMo 설정 (포괄적 인식 모드)
    config = OmegaConf.create({
        'device': device,
        'num_workers': 0,
        'sample_rate': 16000,
        'batch_size': 32,
        'verbose': True,

        'diarizer': {
            'manifest_filepath': str(manifest_path),
            'out_dir': str(work_dir),
            'oracle_vad': False,
            'collar': 0.25,
            'ignore_overlap': False,  # 동시 발화 처리

            'speaker_embeddings': {
                'model_path': 'titanet_large',
                'parameters': {
                    'window_length_in_sec': [2.0, 1.5, 1.0, 0.5],
                    'shift_length_in_sec': [1.0, 0.75, 0.5, 0.25],
                    'multiscale_weights': [0.8, 1.0, 1.0, 0.6],
                    'save_embeddings': False
                }
            },

            'clustering': {
                'parameters': {
                    'oracle_num_speakers': num_speakers is not None,
                    'max_num_speakers': num_speakers if num_speakers is not None else 10,
                    'max_rp_threshold': 0.18,
                    'enhanced_count_thres': 60,
                    'sparse_search_volume': 40
                }
            },

            'vad': {
                'model_path': 'vad_multilingual_marblenet',
                'parameters': {
                    'window_length_in_sec': 0.15,
                    'shift_length_in_sec': 0.01,
                    'smoothing': 'median',
                    'overlap': 0.85,
                    'onset': 0.4,
                    'offset': 0.25,
                    'pad_onset': 0.1,
                    'pad_offset': 0.1,
                    'min_duration_on': 0.08,
                    'min_duration_off': 0.15,
                    'filter_speech_first': True
                }
            }
        }
    })

    print("[Diarization-NeMo] Configuration:")
    print(f"   - Max speakers: 10 (auto detect)")
    print(f"   - Multi-scale: 4 levels (2.0s → 0.5s)")
    print(f"   - VAD: High sensitivity")

    # 3. 화자 분리 실행
    print("[Diarization-NeMo] Running diarization...")
    from nemo.collections.asr.models import ClusteringDiarizer

    diarizer = ClusteringDiarizer(cfg=config)
    diarizer.diarize()

    # 4. RTTM 파일 읽기
    rttm_file = audio_path.stem + ".rttm"
    rttm_path = work_dir / "pred_rttms" / rttm_file

    if not rttm_path.exists():
        raise FileNotFoundError(f"RTTM file not found: {rttm_path}")

    speaker_timestamps = []
    detected_speakers = set()

    with open(rttm_path, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 8:
                start_time = float(parts[3])
                duration = float(parts[4])
                speaker_id = parts[7]

                speaker_timestamps.append({
                    'start': start_time,
                    'end': start_time + duration,
                    'speaker': speaker_id
                })
                detected_speakers.add(speaker_id)

    print(f"[Diarization-NeMo] Detected {len(detected_speakers)} speakers")

    # 5. 화자별 임베딩 추출
    print("[Diarization-NeMo] Extracting speaker embeddings...")

    speaker_model = EncDecSpeakerLabelModel.from_pretrained("titanet_large")
    speaker_model = speaker_model.eval().to(device)

    embeddings_dict = {}

    for speaker_id in detected_speakers:
        # 해당 화자의 가장 긴 세그먼트 3개 선택
        speaker_segments = [ts for ts in speaker_timestamps if ts['speaker'] == speaker_id]
        speaker_segments.sort(key=lambda x: x['end'] - x['start'], reverse=True)
        top_segments = speaker_segments[:min(3, len(speaker_segments))]

        segment_embeddings = []

        for seg in top_segments:
            try:
                # 오디오 로드
                waveform, sr = torchaudio.load(
                    str(audio_path),
                    frame_offset=int(seg['start'] * 16000),
                    num_frames=int((seg['end'] - seg['start']) * 16000)
                )

                # 최소 길이 체크
                if waveform.shape[1] < 1600:  # 0.1초 미만
                    continue

                # 임베딩 추출
                with torch.no_grad():
                    waveform = waveform.to(device)
                    signal_length = torch.tensor([waveform.shape[1]]).to(device)

                    output = speaker_model(input_signal=waveform, input_signal_length=signal_length)

                    # TitaNet은 tuple (logits, emb) 반환
                    if isinstance(output, tuple):
                        emb = output[-1]
                    else:
                        emb = output

                    emb = emb.cpu().numpy()[0]
                    segment_embeddings.append(emb)

            except Exception as e:
                print(f"   ⚠️ {speaker_id} segment skip: {str(e)[:50]}")
                continue

        if not segment_embeddings:
            print(f"   ⚠️ {speaker_id}: No valid embeddings, skipped")
            continue

        # 평균 임베딩 계산
        mean_embedding = np.mean(segment_embeddings, axis=0)

        # L2 정규화
        mean_embedding = mean_embedding / np.linalg.norm(mean_embedding)

        embeddings_dict[speaker_id.upper()] = mean_embedding.tolist()

        print(f"   ✓ {speaker_id.upper()}: {len(segment_embeddings)} segments averaged, dim={len(mean_embedding)}")

    # 6. 결과 변환
    turns = []
    for ts in speaker_timestamps:
        turns.append({
            "speaker_label": ts['speaker'].upper(),
            "start": round(ts['start'], 2),
            "end": round(ts['end'], 2)
        })

    turns.sort(key=lambda x: x['start'])

    result = {
        "turns": turns,
        "embeddings": embeddings_dict
    }

    # 메모리 정리
    del diarizer
    del speaker_model
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    print(f"[Diarization-NeMo] Completed: {len(turns)} segments, {len(embeddings_dict)} speakers")

    return result
