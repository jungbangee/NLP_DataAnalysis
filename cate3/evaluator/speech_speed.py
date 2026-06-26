import re


TIMESTAMP_PATTERN = r"(?:[<\[])?(\d{1,2}:\d{2}(?::\d{2})?)(?:[>\]])?"
RANGE_LINE_PATTERN = re.compile(
    r"^\s*[\[<]?"
    r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?)"
    r"\s*(?:[-~]|-->|–|—|to)\s*"
    r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?)"
    r"[\]>]?\s*(?P<text>.*)$"
)
SINGLE_LINE_PATTERN = re.compile(
    r"^\s*[\[<]?"
    r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?)"
    r"[\]>]?\s*(?P<text>.*)$"
)

SPEED_RUBRIC = [
    {
        "score": 5,
        "label": "appropriate",
        "min_epm": 45,
        "max_epm": 70,
        "reason": "개념 설명을 따라가기에 적절한 발화 속도입니다."
    },
    {
        "score": 4,
        "label": "mostly appropriate",
        "slow_min": 40,
        "slow_max": 44,
        "fast_min": 71,
        "fast_max": 80,
        "reason": "발화 속도가 다소 느리거나 빠르지만 이해에 큰 지장은 없습니다."
    },
    {
        "score": 3,
        "label": "moderate",
        "slow_min": 32,
        "slow_max": 39,
        "fast_min": 81,
        "fast_max": 90,
        "reason": "발화 속도를 이해할 수 있으나 인지 부하가 증가할 수 있습니다."
    },
    {
        "score": 2,
        "label": "needs attention",
        "slow_min": 25,
        "slow_max": 31,
        "fast_min": 91,
        "fast_max": 105,
        "reason": "발화 속도가 너무 느리거나 빨라 학습 효율이 저하될 수 있습니다."
    },
]


def parse_timestamp(ts):
    """Convert hh:mm:ss or mm:ss to seconds."""
    parts = [int(part) for part in ts.split(":")]

    if len(parts) == 2:
        h = 0
        m, s = parts
    else:
        h, m, s = parts

    return h * 3600 + m * 60 + s


def clean_segment_text(text):
    text = text.strip()
    text = re.sub(r"^[^\n:]{1,80}:\s*", "", text).strip()
    return text


def extract_segments(script):
    """
    Extract timestamped utterances.

    Returns:
    [
        (time_in_seconds, text),
        ...
    ]
    """
    segments = []

    for line in script.splitlines():
        range_match = RANGE_LINE_PATTERN.match(line)

        if range_match:
            text = clean_segment_text(range_match.group("text"))

            if text:
                segments.append({
                    "start": parse_timestamp(range_match.group("start")),
                    "end": parse_timestamp(range_match.group("end")),
                    "text": text
                })

            continue

        single_match = SINGLE_LINE_PATTERN.match(line)

        if single_match:
            text = clean_segment_text(single_match.group("text"))

            if text:
                segments.append({
                    "start": parse_timestamp(single_match.group("start")),
                    "end": None,
                    "text": text
                })

    return segments


def count_eojeol(text):
    """Count Korean eojeol-like units using whitespace-separated tokens."""
    return len([token for token in text.split() if token.strip()])


def count_chars(text):
    """Count visible characters except whitespace."""
    return len(re.sub(r"\s+", "", text))


def score_by_epm(epm):
    """Score lecture speech pace by eojeol per minute."""
    if 45 <= epm <= 70:
        return SPEED_RUBRIC[0]

    for rubric in SPEED_RUBRIC[1:]:
        is_slow_range = rubric["slow_min"] <= epm <= rubric["slow_max"]
        is_fast_range = rubric["fast_min"] <= epm <= rubric["fast_max"]

        if is_slow_range or is_fast_range:
            return rubric

    return {
        "score": 1,
        "label": "inappropriate",
        "reason": "발화 속도가 매우 느리거나 빠르며 이해를 방해할 수 있습니다."
    }


def calculate_speech_speed_with_timestamp(script):
    segments = extract_segments(script)

    has_single_timed_segment = (
        len(segments) == 1
        and segments[0]["end"]
        and segments[0]["end"] > segments[0]["start"]
    )

    if not segments or (len(segments) < 2 and not has_single_timed_segment):
        return {
            "epm": 0,
            "cpm": 0,
            "wpm": 0,
            "score": 0,
            "label": "not measurable",
            "reason": (
                "발화 속도를 측정하기 위한 타임스탬프 구간이 충분하지 않습니다. 스크립트에 <00:00:00> 또는 [00:00:00] 형식의 타임스탬프가 포함되어 있는지 확인하세요."
            ),
            "segments": []
        }

    results = []
    total_eojeol = 0
    total_chars = 0
    total_time = 0

    for i in range(len(segments) - 1):
        segment = segments[i]
        next_segment = segments[i + 1]
        start_time = segment["start"]
        end_time = segment["end"] or next_segment["start"]
        text = segment["text"]

        if end_time <= start_time:
            continue

        duration = end_time - start_time

        eojeol_count = count_eojeol(text)
        char_count = count_chars(text)
        epm = eojeol_count / (duration / 60)
        cpm = char_count / (duration / 60)

        results.append({
            "start": start_time,
            "end": end_time,
            "duration_seconds": duration,
            "epm": round(epm, 1),
            "cpm": round(cpm, 1),
            "eojeol": eojeol_count,
            "chars": char_count
        })

        total_eojeol += eojeol_count
        total_chars += char_count
        total_time += duration

    if segments[-1]["end"] and segments[-1]["end"] > segments[-1]["start"]:
        segment = segments[-1]
        duration = segment["end"] - segment["start"]
        eojeol_count = count_eojeol(segment["text"])
        char_count = count_chars(segment["text"])
        epm = eojeol_count / (duration / 60)
        cpm = char_count / (duration / 60)

        results.append({
            "start": segment["start"],
            "end": segment["end"],
            "duration_seconds": duration,
            "epm": round(epm, 1),
            "cpm": round(cpm, 1),
            "eojeol": eojeol_count,
            "chars": char_count
        })

        total_eojeol += eojeol_count
        total_chars += char_count
        total_time += duration

    if total_time <= 0:
        return {
            "epm": 0,
            "cpm": 0,
            "wpm": 0,
            "score": 0,
            "label": "not measurable",
            "segment_count": len(segments),
            "reason": (
                "타임스탬프가 발견되었으나 유효한 시간 구간을 계산할 수 없습니다. 타임스탬프가 시간 순서대로 증가하는지 확인하세요."
            ),
            "segments": results
        }

    overall_epm = total_eojeol / (total_time / 60) if total_time > 0 else 0
    overall_cpm = total_chars / (total_time / 60) if total_time > 0 else 0
    rubric = score_by_epm(overall_epm)

    return {
        "epm": round(overall_epm, 1),
        "cpm": round(overall_cpm, 1),
        # Backward-compatible alias. In this Korean lecture project, this is EPM.
        "wpm": round(overall_epm, 1),
        "score": rubric["score"],
        "label": rubric["label"],
        "segment_count": len(segments),
        "reason": (
            f"분당 {round(overall_epm, 1)} 어절, {round(overall_cpm, 1)} 글자 속도로 측정되었습니다. {rubric['reason']}"
        ),
        "segments": results
    }