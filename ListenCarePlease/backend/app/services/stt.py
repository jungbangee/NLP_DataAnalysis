"""
STT 서비스

Whisper API 기반 음성 전사 시스템
- 청크 분할 (10분 단위)
- Whisper API/로컬 전사
- 타임스탬프 병합
- 중복 제거 후처리
"""
import os
import re
import math
from pathlib import Path
from typing import List, Tuple
from datetime import timedelta
from pydub import AudioSegment
from openai import OpenAI
from app.core.config import settings

try:
    import whisper
    LOCAL_WHISPER_AVAILABLE = True
except ImportError:
    LOCAL_WHISPER_AVAILABLE = False
    print("⚠️ openai-whisper not installed. Install with: pip install openai-whisper")


SAMPLE_RATE = 16000
CHUNK_MINUTES = 10
MAX_TARGET_MB = 25

re_srt_block = re.compile(
    r"(\d+)\s+([\d:,]{12} --> [\d:,]{12})\s+(.+?)(?=\n\d+\n|\Z)", re.S
)
re_line = re.compile(
    r"^\[(\d{2}:\d{2}:\d{2}\.\d{3})\s*-\s*(\d{2}:\d{2}:\d{2}\.\d{3})\]\s*(.*)$"
)

_whisper_model_cache = {}


def ms_to_srt_time(ms: int) -> str:
    """밀리초 → SRT 시간 형식 변환"""
    td = timedelta(milliseconds=ms)
    hours, rem = divmod(td.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    hours += td.days * 24
    millis = int(ms % 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def srt_time_to_ms(t: str) -> int:
    """SRT 시간 형식 → 밀리초 변환"""
    t = t.replace(",", ".")
    h, m, rest = t.split(":")
    s, ms = rest.split(".")
    return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)


def parse_srt(srt_text: str) -> List[Tuple[str, str, str]]:
    """SRT 파서: (start, end, text) 리스트 반환"""
    blocks = []
    for m in re_srt_block.finditer(srt_text):
        idx = m.group(1)
        times = m.group(2)
        text = m.group(3).strip()
        st_str, et_str = [x.strip() for x in times.split("-->")]
        blocks.append((st_str, et_str, text))
    return blocks


def parse_line(line: str) -> Tuple[str, str, str]:
    """타임스탬프 라인 파싱"""
    m = re_line.match(line.strip())
    if not m:
        return ("", "", line.strip())
    return m.group(1), m.group(2), m.group(3)


def normalize_text(s: str) -> str:
    """공백 정규화"""
    s = re.sub(r"\s+", " ", s).strip()
    return s


def collapse_sentence_runs(text: str) -> str:
    """같은 문장 반복 축약"""
    s = normalize_text(text)
    sentences = re.split(r"(?<=[.!?])\s+", s)
    out = []
    last = None
    for sen in sentences:
        if sen and sen != last:
            out.append(sen)
            last = sen
    return " ".join(out)


def collapse_word_runs(text: str) -> str:
    """같은 단어 반복 축약"""
    toks = text.split()
    out = []
    last = None
    for t in toks:
        if last is None or t != last:
            out.append(t)
            last = t
    return " ".join(out)


def dedup_inside_line(text: str) -> str:
    """라인 내부 중복 제거"""
    s = collapse_sentence_runs(text)
    s = collapse_word_runs(s)
    s = normalize_text(s)
    return s


def norm_for_compare(s: str) -> str:
    """비교를 위한 정규화"""
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"(\.){2,}$", ".", s)
    return s


def split_audio_chunks(
    preprocessed_wav: Path, chunk_dir: Path, chunk_minutes: int = CHUNK_MINUTES
) -> List[Path]:
    """
    전처리된 WAV를 청크로 분할

    Args:
        preprocessed_wav: 전처리된 WAV 파일
        chunk_dir: 청크 저장 디렉토리
        chunk_minutes: 청크 길이(분)

    Returns:
        청크 파일 경로 리스트
    """
    chunk_dir.mkdir(parents=True, exist_ok=True)

    audio = AudioSegment.from_file(preprocessed_wav)
    total_ms = len(audio)

    chunk_ms = chunk_minutes * 60 * 1000
    n_chunks = math.ceil(total_ms / chunk_ms)

    exported: List[Path] = []

    for i in range(n_chunks):
        start_ms = i * chunk_ms
        end_ms = min((i + 1) * chunk_ms, total_ms)
        seg = audio[start_ms:end_ms]

        wav_path = chunk_dir / f"chunk_{i:04d}.wav"
        seg.export(wav_path, format="wav", parameters=["-ar", str(SAMPLE_RATE), "-ac", "1"])

        size_mb = wav_path.stat().st_size / (1024 * 1024)
        if size_mb >= MAX_TARGET_MB:
            print(f"⚠️ chunk_{i:04d}.wav: {size_mb:.2f}MB (25MB 근접)")

        exported.append(wav_path)

    return exported


def transcribe_single_chunk_local(
    chunk_path: Path, srt_dir: Path, chunk_num: int, total_chunks: int,
    model_size: str = "large", device: str = "cpu"
) -> Path:
    """
    단일 청크를 로컬 Whisper로 전사

    Args:
        chunk_path: 청크 WAV 파일 경로
        srt_dir: SRT 저장 디렉토리
        chunk_num: 청크 번호 (1부터 시작)
        total_chunks: 전체 청크 개수
        model_size: Whisper 모델 크기 (tiny, base, small, medium, large)
        device: 디바이스 (cuda, cpu)

    Returns:
        SRT 파일 경로
    """
    import time
    import torch

    if not LOCAL_WHISPER_AVAILABLE:
        raise ImportError("openai-whisper is not installed")

    if device == "cuda" and not torch.cuda.is_available():
        print("⚠️ CUDA requested but not available. Falling back to CPU.")
        device = "cpu"

    size_mb = chunk_path.stat().st_size / (1024 * 1024)
    print(f"▶️ {chunk_num}/{total_chunks} Local Whisper 전사 시작: {chunk_path.name} ({size_mb:.2f}MB, device: {device})")

    try:
        start_time = time.time()

        model_key = f"{model_size}_{device}"
        if model_key not in _whisper_model_cache:
            print(f"📥 모델 로딩: {model_size} ({device})")
            _whisper_model_cache[model_key] = whisper.load_model(model_size, device=device)

        model = _whisper_model_cache[model_key]

        result = model.transcribe(
            str(chunk_path),
            language="ko",
            verbose=False
        )

        srt_lines = []
        segment_num = 1
        for segment in result["segments"]:
            start = format_timestamp(segment["start"])
            end = format_timestamp(segment["end"])
            text = segment["text"].strip()

            srt_lines.append(f"{segment_num}")
            srt_lines.append(f"{start} --> {end}")
            srt_lines.append(text)
            srt_lines.append("")
            segment_num += 1

        srt_text = "\n".join(srt_lines)

        elapsed = time.time() - start_time
        print(f"✅ {chunk_path.name} 완료 ({elapsed:.1f}초)")

        srt_path = srt_dir / f"{chunk_path.stem}.srt"
        srt_path.write_text(srt_text, encoding="utf-8")
        return srt_path

    except Exception as e:
        print(f"❌ {chunk_path.name} 전사 실패: {e}")
        raise


def format_timestamp(seconds: float) -> str:
    """초를 SRT 타임스탬프 형식으로 변환"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def transcribe_chunks_with_local_whisper(
    chunk_files: List[Path], srt_dir: Path,
    model_size: str = "large", device: str = "cpu"
) -> List[Path]:
    """
    청크들을 로컬 Whisper로 순차 전사

    Note: GPU 메모리 사용량이 높아 병렬 처리 대신 순차 처리

    Args:
        chunk_files: 청크 WAV 파일 리스트
        srt_dir: SRT 저장 디렉토리
        model_size: Whisper 모델 크기
        device: 디바이스 (cuda, cpu)

    Returns:
        SRT 파일 경로 리스트 (순서 보장)
    """
    import time

    srt_dir.mkdir(parents=True, exist_ok=True)

    print(f"🚀 로컬 전사 시작: {len(chunk_files)}개 청크 (모델: {model_size}, 디바이스: {device})")
    start_time = time.time()

    srt_files = []
    for i, chunk_path in enumerate(chunk_files):
        srt_path = transcribe_single_chunk_local(
            chunk_path, srt_dir, i + 1, len(chunk_files), model_size, device
        )
        srt_files.append(srt_path)

    elapsed = time.time() - start_time
    print(f"✅ 전체 전사 완료 ({elapsed:.1f}초)")

    return srt_files


def transcribe_single_chunk(
    chunk_path: Path, srt_dir: Path, openai_api_key: str, chunk_num: int, total_chunks: int
) -> Path:
    """
    단일 청크를 Whisper API로 전사

    Args:
        chunk_path: 청크 WAV 파일 경로
        srt_dir: SRT 저장 디렉토리
        openai_api_key: OpenAI API 키
        chunk_num: 청크 번호 (1부터 시작)
        total_chunks: 전체 청크 개수

    Returns:
        SRT 파일 경로
    """
    import time

    client = OpenAI(api_key=openai_api_key, timeout=1800.0)
    size_mb = chunk_path.stat().st_size / (1024 * 1024)

    print(f"▶️ {chunk_num}/{total_chunks} Whisper 전사 시작: {chunk_path.name} ({size_mb:.2f}MB)")

    try:
        start_time = time.time()
        with chunk_path.open("rb") as f:
            srt_text = client.audio.transcriptions.create(
                model="whisper-1",
                file=(chunk_path.name, f, "audio/wav"),
                language="ko",
                response_format="srt"
            )
        elapsed = time.time() - start_time
        print(f"✅ {chunk_path.name} 완료 ({elapsed:.1f}초)")

        srt_path = srt_dir / f"{chunk_path.stem}.srt"
        srt_path.write_text(srt_text, encoding="utf-8")
        return srt_path

    except Exception as e:
        print(f"❌ {chunk_path.name} 전사 실패: {e}")
        raise


def transcribe_chunks_with_whisper(
    chunk_files: List[Path], srt_dir: Path, openai_api_key: str
) -> List[Path]:
    """
    청크들을 Whisper API로 병렬 전사

    Args:
        chunk_files: 청크 WAV 파일 리스트
        srt_dir: SRT 저장 디렉토리
        openai_api_key: OpenAI API 키

    Returns:
        SRT 파일 경로 리스트 (순서 보장)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import time

    os.environ["OPENAI_API_KEY"] = openai_api_key
    srt_dir.mkdir(parents=True, exist_ok=True)

    print(f"🚀 병렬 전사 시작: {len(chunk_files)}개 청크")
    start_time = time.time()

    srt_files_dict = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_chunk = {
            executor.submit(
                transcribe_single_chunk,
                cp,
                srt_dir,
                openai_api_key,
                i + 1,
                len(chunk_files)
            ): (i, cp)
            for i, cp in enumerate(chunk_files)
        }

        for future in as_completed(future_to_chunk):
            idx, chunk_path = future_to_chunk[future]
            try:
                srt_path = future.result()
                srt_files_dict[idx] = srt_path
            except Exception as e:
                print(f"❌ 전사 실패: {chunk_path.name} - {e}")
                raise

    srt_files = [srt_files_dict[i] for i in sorted(srt_files_dict.keys())]

    elapsed = time.time() - start_time
    print(f"✅ 전체 전사 완료 ({elapsed:.1f}초)")

    return srt_files


def merge_timestamps(
    chunk_files: List[Path], srt_files: List[Path], output_txt: Path
) -> Path:
    """
    청크별 SRT를 하나의 타임스탬프 TXT로 병합

    Args:
        chunk_files: 청크 WAV 파일 리스트
        srt_files: 청크별 SRT 파일 리스트
        output_txt: 출력 TXT 경로

    Returns:
        병합된 TXT 경로
    """
    offsets = []
    acc = 0
    for cp in chunk_files:
        dur_ms = len(AudioSegment.from_file(cp))
        offsets.append(acc)
        acc += dur_ms

    all_lines = []
    for idx, srt_path in enumerate(srt_files):
        srt_text = srt_path.read_text(encoding="utf-8")
        cues = parse_srt(srt_text)
        off = offsets[idx]

        for st, et, text in cues:
            st_ms = srt_time_to_ms(st) + off
            et_ms = srt_time_to_ms(et) + off
            clean_text = text.replace('\n', ' ')
            one_line = f"[{ms_to_srt_time(st_ms)} - {ms_to_srt_time(et_ms)}] {clean_text}"
            all_lines.append(one_line)

    output_txt.parent.mkdir(parents=True, exist_ok=True)
    output_txt.write_text("\n".join(all_lines), encoding="utf-8")

    return output_txt


def postprocess_transcript(input_txt: Path, output_txt: Path) -> Path:
    """
    타임스탬프 TXT 후처리 (중복 제거)

    Args:
        input_txt: 입력 TXT
        output_txt: 출력 TXT

    Returns:
        후처리된 TXT 경로
    """
    raw_lines = input_txt.read_text(encoding="utf-8", errors="ignore").splitlines()
    entries = []
    for ln in raw_lines:
        st, et, tx = parse_line(ln)
        tx = dedup_inside_line(tx)
        entries.append({"start": st, "end": et, "text": tx})

    kept = []
    removed = 0
    for cur in entries:
        cur_txt = cur["text"]
        cur_norm = norm_for_compare(cur_txt)

        dup = False
        for prev in kept:
            prev_norm = norm_for_compare(prev["text"])
            if cur_norm == prev_norm:
                dup = True
                break
            if cur_norm in prev_norm or prev_norm in cur_norm:
                dup = True
                break

        if dup:
            removed += 1
        else:
            kept.append(cur)

    out_lines = []
    for e in kept:
        st = e["start"] or "00:00:00.000"
        et = e["end"] or "00:00:00.000"
        out_lines.append(f"[{st} - {et}] {e['text']}")

    output_txt.parent.mkdir(parents=True, exist_ok=True)
    output_txt.write_text("\n".join(out_lines), encoding="utf-8")

    print(f"[후처리] 입력: {len(entries)}, 제거: {removed}, 남음: {len(kept)}")

    return output_txt


def run_stt_pipeline(
    preprocessed_wav: Path, work_dir: Path, openai_api_key: str = None,
    use_local_whisper: bool = True, model_size: str = "large",
    device: str = "cpu"
) -> Path:
    """
    STT 전체 파이프라인 실행

    Args:
        preprocessed_wav: 전처리된 WAV 파일
        work_dir: 작업 디렉토리
        openai_api_key: OpenAI API 키 (use_local_whisper=False일 때 필요)
        use_local_whisper: 로컬 Whisper 사용 여부 (기본값: True)
        model_size: 로컬 Whisper 모델 크기 (tiny, base, small, medium, large)
        device: 디바이스 (cpu, cuda)

    Returns:
        최종 전사 TXT 파일 경로
    """
    chunk_dir = work_dir / "chunks"
    srt_dir = work_dir / "srt"
    merged_txt = work_dir / "merged_transcript.txt"
    final_txt = work_dir / "final_transcript.txt"

    print("[STT Step 1] 청크 분할...")
    chunk_files = split_audio_chunks(preprocessed_wav, chunk_dir)
    print(f"✅ {len(chunk_files)}개 청크 생성")

    if use_local_whisper:
        print(f"[STT Step 2] Local Whisper 전사 (모델: {model_size}, 디바이스: {device})...")
        srt_files = transcribe_chunks_with_local_whisper(
            chunk_files, srt_dir, model_size, device
        )
    else:
        print("[STT Step 2] OpenAI Whisper 전사...")
        if not openai_api_key:
            raise ValueError("OpenAI API key is required when use_local_whisper=False")
        srt_files = transcribe_chunks_with_whisper(chunk_files, srt_dir, openai_api_key)
    print(f"✅ {len(srt_files)}개 SRT 생성")

    print("[STT Step 3] 타임스탬프 병합...")
    merge_timestamps(chunk_files, srt_files, merged_txt)
    print(f"✅ 병합 완료 → {merged_txt}")

    print("[STT Step 4] 후처리 (중복 제거)...")
    postprocess_transcript(merged_txt, final_txt)
    print(f"✅ 최종 전사 완료 → {final_txt}")

    return final_txt
