"""
utils.py - STT 파일 파싱 및 구간 추출 유틸리티
eda_visualize.py의 파싱 로직을 재사용하여 구현
"""
import re
from pathlib import Path

DATA_DIR = Path(r"C:\Users\HS\Documents\Claude\lecture-analysis-project\강의 스크립트")


def parse_file(fname: str) -> list[str]:
    """파일을 읽어서 비어있지 않은 줄 목록 반환 (eda_visualize.py 재사용)"""
    path = DATA_DIR / fname if not Path(fname).is_absolute() else Path(fname)
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    return [line.strip() for line in lines if line.strip()]


def parse_text(lecture_text: str) -> list[str]:
    """
    웹 업로드 텍스트를 직접 받아 parse_file()과 동일한 줄 목록을 반환합니다.

    Args:
        lecture_text: 업로드된 txt 파일의 텍스트 내용

    Returns:
        비어있지 않은 줄 목록 (parse_file()과 동일한 형식)
    """
    return [line.strip() for line in lecture_text.splitlines() if line.strip()]


def get_lines(fname: str = "", lecture_text: str = "") -> list[str]:
    """
    파일 경로 또는 텍스트 중 하나를 받아 줄 목록을 반환하는 통합 헬퍼.

    v7/v8에서 parse_file(fname) 대신 이 함수를 사용하면
    로컬 파일과 웹 업로드 텍스트를 동일하게 처리할 수 있습니다.

    사용 예시:
        lines = get_lines(fname="2026-02-02_강의.txt")          # 로컬 파일
        lines = get_lines(lecture_text=uploaded_text)           # 웹 업로드
    """
    if lecture_text:
        return parse_text(lecture_text)
    if fname:
        return parse_file(fname)
    raise ValueError("fname 또는 lecture_text 중 하나는 반드시 제공해야 합니다.")


def get_utterances(lines: list[str]) -> list[str]:
    """타임스탬프(<HH:MM:SS>)가 있는 발화만 필터 (eda_visualize.py 재사용)"""
    return [line for line in lines if re.search(r"<\d{2}:\d{2}:\d{2}>", line)]


def parse_time(time_str: str) -> int:
    """HH:MM:SS → 초(int)로 변환 (eda_visualize.py 재사용)"""
    h, m, s = map(int, time_str.split(":"))
    return h * 3600 + m * 60 + s


def get_start_time(utterance: str) -> int | None:
    """발화 한 줄에서 타임스탬프를 초로 변환. 없으면 None"""
    m = re.search(r"<(\d{2}:\d{2}:\d{2})>", utterance)
    return parse_time(m.group(1)) if m else None


def extract_opening(lines: list[str], minutes: int = 10) -> str:
    """강의 시작 후 N분 이내 발화 추출"""
    utts = get_utterances(lines)
    if not utts:
        return ""

    start_time = get_start_time(utts[0])
    if start_time is None:
        return "\n".join(utts[:80])

    cutoff = start_time + minutes * 60
    result = []
    for utt in utts:
        t = get_start_time(utt)
        if t is not None:
            # 자정 넘김 보정 (09:xx → 04:xx 같은 경우)
            adjusted_t = t if t >= start_time else t + 86400
            if adjusted_t <= cutoff:
                result.append(utt)
    return "\n".join(result)


def normalize_timestamps(utts: list[str]) -> list[tuple[int, str]]:
    """
    12시간 형식 타임스탬프 정규화 (09:xx → 12:xx → 01:xx PM 순서 처리)
    STT 파일의 타임스탬프가 12시간제(AM/PM 없음)일 때, 오후 구간을 +43200초로 보정.
    반환: [(정규화된 초, 발화문자열), ...]
    """
    pairs = []
    offset = 0  # 12시간 보정 누적값

    for utt in utts:
        t = get_start_time(utt)
        if t is None:
            continue
        # 직전 타임스탬프보다 크게 감소하면 12시간 넘은 것으로 판단
        if pairs and (t + offset) < (pairs[-1][0] - 60):  # 1분 이상 역행 시
            offset += 43200  # +12시간
        pairs.append((t + offset, utt))

    return pairs


def extract_closing(lines: list[str], minutes: int = 10) -> str:
    """강의 종료 전 N분 발화 추출 (12시간 형식 타임스탬프 보정 포함)"""
    utts = get_utterances(lines)
    if not utts:
        return ""

    pairs = normalize_timestamps(utts)
    if not pairs:
        return "\n".join(utts[-80:])

    end_time = pairs[-1][0]
    cutoff = end_time - minutes * 60

    result = [utt for norm_t, utt in pairs if norm_t >= cutoff]
    return "\n".join(result)


def extract_sampled(lines: list[str], sections: int = 5, per_section: int = 30) -> str:
    """전체 강의를 N개 구간으로 균등 분할 후 각 구간 앞부분 추출 (전체 흐름 파악용)"""
    utts = get_utterances(lines)
    if not utts:
        return ""

    chunk_size = max(1, len(utts) // sections)
    result = []
    for i in range(sections):
        start = i * chunk_size
        end = min(start + per_section, len(utts))
        chunk = utts[start:end]
        if chunk:
            # 구간 구분 헤더 추가
            result.append(f"\n--- 구간 {i+1}/{sections} (발화 #{start+1} ~ #{min(start+per_section, len(utts))}) ---")
            result.extend(chunk)
    return "\n".join(result)


def extract_full(lines: list[str]) -> str:
    """전체 발화를 타임스탬프 포함하여 반환.
    설명 순서(2.3)·핵심 강조(2.4)처럼 '강의 전체의 성질'을 보는 항목용.
    (샘플링으로 worked example/강조를 놓치는 타당성 문제 방지)"""
    return "\n".join(get_utterances(lines))


def format_segment_info(segment: str) -> str:
    """구간 토큰 추정치 출력용 (디버그용)"""
    char_count = len(segment)
    estimated_tokens = char_count // 3  # 한국어 기준 대략 3자/토큰
    return f"[구간 정보: {len(segment.splitlines())}줄, ~{char_count:,}자, 추정 {estimated_tokens:,} 토큰]"


# ── 웹 업로드 텍스트용 extract 래퍼 ──────────────────────────────────
# 기존 extract_* 함수들은 parse_file()로 읽은 lines를 받으므로,
# 웹 업로드 텍스트를 바로 넘길 수 있는 래퍼를 제공합니다.

def extract_opening_from_text(lecture_text: str, minutes: int = 10) -> str:
    """웹 업로드 텍스트에서 강의 시작 후 N분 이내 발화 추출."""
    return extract_opening(parse_text(lecture_text), minutes)


def extract_closing_from_text(lecture_text: str, minutes: int = 10) -> str:
    """웹 업로드 텍스트에서 강의 종료 전 N분 발화 추출."""
    return extract_closing(parse_text(lecture_text), minutes)


def extract_sampled_from_text(lecture_text: str, sections: int = 5, per_section: int = 30) -> str:
    """웹 업로드 텍스트에서 균등 샘플링 추출."""
    return extract_sampled(parse_text(lecture_text), sections, per_section)


def extract_full_from_text(lecture_text: str) -> str:
    """웹 업로드 텍스트에서 전체 발화 추출."""
    return extract_full(parse_text(lecture_text))