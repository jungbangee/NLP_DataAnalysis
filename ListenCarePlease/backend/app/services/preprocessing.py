"""
오디오 전처리 서비스 (I,O.md Step 2)
- ffmpeg 변환 (16kHz, mono)
- HPF (고주파 필터)
- VAD (음성 구간 추출)
- 정규화
"""
import subprocess
from pathlib import Path
from typing import Tuple
import numpy as np
import soundfile as sf
import webrtcvad
from scipy.signal import butter, sosfiltfilt


# 전처리 설정
SR = 16000
HPF_CUTOFF = 80.0
HPF_ORDER = 4
VAD_AGGR = 2
FRAME_MS = 20
PAD_MS = 150
TARGET_PEAK = 0.98


def highpass_hz_80(audio: np.ndarray, sr: int) -> np.ndarray:
    """80Hz 고주파 필터 적용"""
    sos = butter(HPF_ORDER, HPF_CUTOFF, btype="highpass", fs=sr, output="sos")
    return sosfiltfilt(sos, audio).astype(np.float32)


def float_to_int16(x: np.ndarray) -> np.ndarray:
    """Float32 → Int16 변환"""
    x = np.clip(x, -1.0, 1.0)
    return (x * 32767.0).astype(np.int16)


def int16_to_float(x: np.ndarray) -> np.ndarray:
    """Int16 → Float32 변환"""
    return (x.astype(np.float32) / 32767.0)


def frame_bytes_from_int16(x_i16: np.ndarray, sr: int, frame_ms: int):
    """프레임 단위로 바이트 분할"""
    frame_len = int(sr * frame_ms / 1000)
    step = frame_len
    n = len(x_i16)
    i = 0
    while i + frame_len <= n:
        yield (i, x_i16[i : i + frame_len].tobytes())
        i += step


def vad_keep_mask(
    audio_f32: np.ndarray, sr: int, frame_ms: int, vad_aggr: int, pad_ms: int
):
    """
    webrtcvad로 음성 구간만 남기는 마스크 계산
    """
    x_i16 = float_to_int16(audio_f32)
    vad = webrtcvad.Vad(vad_aggr)
    frame_iter = list(frame_bytes_from_int16(x_i16, sr, frame_ms))
    n_frames = len(frame_iter)

    voiced = np.zeros(n_frames, dtype=bool)
    for i, (start, frame_bytes) in enumerate(frame_iter):
        if vad.is_speech(frame_bytes, sr):
            voiced[i] = True

    pad_frames = pad_ms // frame_ms
    keep = np.zeros_like(voiced)
    for i, v in enumerate(voiced):
        if v:
            s = max(0, i - pad_frames)
            e = min(n_frames, i + pad_frames + 1)
            keep[s:e] = True

    frame_len = int(sr * frame_ms / 1000)
    keep_samples = np.repeat(keep, frame_len)
    keep_samples = keep_samples[: len(x_i16)]
    keep_samples = keep_samples[: len(audio_f32)]
    if len(keep_samples) < len(audio_f32):
        keep_samples = np.pad(
            keep_samples,
            (0, len(audio_f32) - len(keep_samples)),
            mode="constant",
        )

    return keep_samples


def peak_normalize(x: np.ndarray, target_peak: float = 0.98) -> np.ndarray:
    """피크 정규화"""
    peak = np.max(np.abs(x)) + 1e-12
    g = target_peak / peak
    y = np.clip(x * g, -1.0, 1.0)
    return y.astype(np.float32)


def preprocess_audio(
    input_path: Path, output_path: Path
) -> Tuple[Path, float, float]:
    """
    오디오 전처리 파이프라인

    Args:
        input_path: 입력 오디오 파일 경로
        output_path: 출력 WAV 파일 경로

    Returns:
        (output_path, 원본 길이(초), 전처리 후 길이(초))
    """
    # 1) ffmpeg 변환 (16kHz, mono)
    temp_converted = output_path.parent / f"temp_converted_{output_path.stem}.wav"
    temp_converted.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(input_path),
                "-ar",
                "16000",
                "-ac",
                "1",
                "-acodec",
                "pcm_s16le",
                str(temp_converted),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg 변환 실패: {e.stderr.decode('utf-8', errors='ignore')}")

    # 2) 전처리 (HPF + VAD + Normalize)
    audio, sr = sf.read(str(temp_converted), always_2d=False)
    if sr != SR:
        raise ValueError(f"입력 SR={sr}가 16kHz가 아닙니다.")
    if audio.ndim != 1:
        raise ValueError("입력이 mono가 아닙니다.")
    audio = audio.astype(np.float32)

    original_duration = len(audio) / SR

    # HPF 적용
    audio_hpf = highpass_hz_80(audio, SR)

    # VAD 적용
    mask = vad_keep_mask(audio_hpf, SR, FRAME_MS, VAD_AGGR, PAD_MS)
    voiced = audio_hpf[mask]

    # VAD로 너무 많이 제거된 경우 fallback
    if voiced.size < int(0.1 * len(audio_hpf)) and len(audio_hpf) > 0:
        voiced = audio_hpf

    # 정규화
    voiced_norm = peak_normalize(voiced, TARGET_PEAK)

    processed_duration = len(voiced_norm) / SR

    # 3) 저장
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_path), voiced_norm, SR, subtype="PCM_16")

    # 임시 파일 삭제
    if temp_converted.exists():
        temp_converted.unlink()

    return output_path, original_duration, processed_duration
