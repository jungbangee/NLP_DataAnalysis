"""
강의 품질 분석 시스템 (STT 텍스트 기반)
=============================================
STT 변환 텍스트를 pandas DataFrame으로 파싱하여
6가지 평가 지표에 가중치를 적용해 종합 점수를 산출합니다.

사용법:
    python lecture_analyzer.py --file <STT파일경로>
    python lecture_analyzer.py --file sample_stt.txt
"""

import re
import sys
import argparse
import warnings
from collections import Counter
from datetime import datetime
from typing import Optional

import pandas as pd
import os as _os


def _call_gemini(prompt: str, model: str, max_tokens: int = 1000) -> str:
    """
    Gemini API 호출 헬퍼.
    환경변수 GEMINI_API_KEY 필요.
    JSON 응답에서 마크다운 펜스와 불필요한 텍스트를 제거 후 반환.

    응답 파싱 방어 처리:
    - candidates 없음 → promptFeedback 차단 (SAFETY 등)
    - content 없음 또는 parts 없음 → finishReason 확인 후 예외
    - parts가 빈 배열 → MAX_TOKENS 초과 등
    - JSON 잘림/형식 오류 → _repair_json()으로 복구 시도
    """
    import json as _json
    import urllib.request as _req

    api_key = _os.environ.get("GEMINI_API_KEY", "")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta"
        f"/models/{model}:generateContent?key={api_key}"
    )
    # Gemini는 응답이 길어질 수 있으므로 여유있게 설정
    # (분석 항목이 많은 발화 + feedback 객체까지 모두 담기에 충분한 여유를 둠)
    safe_max_tokens = max(max_tokens, 3500)

    payload = _json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": safe_max_tokens},
    }).encode("utf-8")

    req = _req.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with _req.urlopen(req, timeout=30) as resp:
        body = _json.loads(resp.read().decode("utf-8"))

    # ── 응답 구조 방어 파싱 ──
    candidates = body.get("candidates", [])
    if not candidates:
        feedback    = body.get("promptFeedback", {})
        block_reason = feedback.get("blockReason", "UNKNOWN")
        raise ValueError(f"Gemini 응답 차단: {block_reason}")

    candidate     = candidates[0]
    finish_reason = candidate.get("finishReason", "")

    content = candidate.get("content", {})
    if not content:
        raise ValueError(f"Gemini content 없음 (finishReason: {finish_reason})")

    parts = content.get("parts", [])
    if not parts:
        raise ValueError(f"Gemini parts 없음 (finishReason: {finish_reason})")

    raw = parts[0].get("text", "").strip()
    if not raw:
        raise ValueError(f"Gemini text 비어있음 (finishReason: {finish_reason})")

    # ── 후처리 1: 마크다운 펜스 제거 ──
    raw = re.sub(r"^```json\s*|^```\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()

    # ── 후처리 2: JSON 블록만 추출 (앞뒤 설명 텍스트 제거) ──
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        raw = match.group(0)

    # ── 후처리 3: JSON 복구 시도 ──
    raw = _repair_json(raw, finish_reason)

    return raw


def _repair_json(raw: str, finish_reason: str = "") -> str:
    """
    Gemini 응답의 JSON 형식 오류를 복구합니다.

    처리하는 케이스:
    1. MAX_TOKENS로 잘린 JSON → 열린 괄호/따옴표 닫기
    2. JSON5 형식 → 표준 JSON으로 변환
       - 따옴표 없는 키: {key: value} → {"key": value}
       - 후행 쉼표: [1, 2,] → [1, 2]
       - 단일 따옴표: {'key': 'value'} → {"key": "value"}
    3. 문자열 값 내부의 작은따옴표 충돌 → 이스케이프 처리
    4. 한국어 키 따옴표 없음 → 이중 따옴표 추가
    """
    import json as _json

    # 먼저 그대로 파싱 시도
    try:
        _json.loads(raw)
        return raw
    except _json.JSONDecodeError:
        pass

    repaired = raw

    # ── 수정 1: 문자열 값 내부 작은따옴표 이스케이프 ──
    # "patterns": ["연속반복: '이제'"] 에서 내부 '이제' 가 충돌하는 경우
    # 이중 따옴표로 감싼 문자열 내부의 작은따옴표를 제거
    def _remove_inner_quotes(m):
        inner = m.group(1)
        inner = inner.replace("'", "")
        return f'"{inner}"'
    repaired = re.sub(r'"([^"]*\'[^"]*)"', _remove_inner_quotes, repaired)

    # ── 수정 2: 전체가 단일 따옴표로 된 경우 → 이중 따옴표 ──
    # 단, 이미 이중 따옴표 안에 있는 단일 따옴표는 건드리지 않음
    try:
        _json.loads(repaired)
        return repaired
    except _json.JSONDecodeError:
        pass

    # 이중 따옴표가 거의 없고 단일 따옴표가 많으면 전체 교체
    if repaired.count("'") > repaired.count('"') * 2:
        repaired = re.sub(r"'([^']*)'", r'"\1"', repaired)

    # ── 수정 3: 따옴표 없는 키 → 이중 따옴표 키 (한국어 포함) ──
    repaired = re.sub(
        r'(?<=[{,])\s*([a-zA-Z_\uAC00-\uD7A3][a-zA-Z0-9_\uAC00-\uD7A3]*)\s*:',
        r' "\1":',
        repaired
    )

    # ── 수정 4: 후행 쉼표 제거 ──
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)

    # 수정 후 파싱 시도
    try:
        _json.loads(repaired)
        return repaired
    except _json.JSONDecodeError:
        pass

    # ── 수정 5: MAX_TOKENS로 잘린 경우 → 괄호/따옴표 닫기 ──
    repaired = _close_truncated_json(repaired)

    return repaired


def _close_truncated_json(raw: str) -> str:
    """
    잘린 JSON의 열린 괄호와 따옴표를 닫아 파싱 가능한 상태로 복구합니다.
    완벽한 복구보다 파싱 가능한 최소한의 구조 확보가 목적입니다.
    """
    import json as _json

    # 잘린 문자열 끝의 불완전한 값 제거
    # 예: "text": "예를 들어서 → "text": "" 로 처리
    raw = re.sub(r':\s*"[^"]*$', ': ""', raw)
    raw = re.sub(r':\s*\[[^\]]*$', ': []', raw)

    # 스택 기반으로 열린 괄호/따옴표 추적 후 닫기
    stack = []
    in_string = False
    escape = False

    for ch in raw:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not in_string:
            in_string = True
        elif ch == '"' and in_string:
            in_string = False
        elif not in_string:
            if ch in "{[":
                stack.append(ch)
            elif ch == "}" and stack and stack[-1] == "{":
                stack.pop()
            elif ch == "]" and stack and stack[-1] == "[":
                stack.pop()

    # 열린 문자열 닫기
    if in_string:
        raw += '"'

    # 열린 배열/객체 역순으로 닫기
    for ch in reversed(stack):
        raw += "}" if ch == "{" else "]"

    try:
        _json.loads(raw)
        return raw
    except _json.JSONDecodeError:
        # 복구 실패 시 원본 반환 (호출부 except에서 폴백 처리)
        return raw

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────
# 1. 평가 지표 설정 (가중치 합계 = 1.0)
# ─────────────────────────────────────────
CRITERIA = {
    "불필요한_반복_표현":   {"weight": 0.20, "higher_is_better": False},
    "발화_완결성":          {"weight": 0.20, "higher_is_better": True},
    "언어_일관성":          {"weight": 0.15, "higher_is_better": True},
    "이해_확인_질문":       {"weight": 0.20, "higher_is_better": True},
    "참여_유도":            {"weight": 0.15, "higher_is_better": True},
    "질문_응답_충분성":     {"weight": 0.10, "higher_is_better": True},
}

# ─────────────────────────────────────────
# 2. 루브릭 기준표 (5점 척도)
# ─────────────────────────────────────────
# 각 지표별 1~5점 기준을 명문화합니다.
# 실제 강의 데이터를 통해 기준값을 지속적으로 검증/수정하세요.
#
# 구조: { 지표명: { 점수: (조건설명, 판정함수) } }
# 판정함수는 analyze_* 함수의 결과 딕셔너리(r)를 받아 bool 반환

def _rubric_score(r: dict, criterion: str) -> float:
    """
    루브릭 기준표에 따라 1.0~5.0점 반환 (소수점 연속 점수).

    정규화 방식:
    - 각 지표의 핵심 수치를 루브릭 구간(1~5)에 선형 보간(interpolate)
    - 구간 경계값 사이에서 연속적인 점수 산출 → 계단식 급변 방지
    - 결과는 소수점 2자리로 반올림 후 1.0~5.0 범위로 클램핑

    예시: 미완결 발화 2건 → 4점 구간(2~3건) 안에서 4.5점
          미완결 발화 3건 → 4점 구간 하한 → 4.0점
    """

    def _interpolate(value, low, high, score_low, score_high):
        """value가 [low, high] 구간에 있을 때 [score_low, score_high]로 선형 보간."""
        if high == low:
            return score_low
        ratio = (value - low) / (high - low)
        return score_high + (score_low - score_high) * ratio

    def _clamp(v):
        return round(max(1.0, min(5.0, v)), 2)

    # ── 불필요한 반복 표현 ──
    # 핵심 지표: 필러 어휘 건수 (페널티 비율은 보조)
    if criterion == "불필요한_반복_표현":
        total   = max(r.get("total_instructor_turns", 1), 1)
        penalty = r.get("penalty_count", 0)   # 실제 연속 반복 패턴 건수
        fillers = sum(r.get("filler_word_counts", {}).values())
        ratio   = penalty / total * 100   # 퍼센트

        # 핵심 기준: 연속 반복 패턴(penalty_count) 건수
        # 단순 필러 빈도는 보조 감점으로만 활용
        # 구간: 0건 → 5점, 1~2건 → 4점, 3~5건 → 3점, 6~8건 → 2점, 9건+ → 1점
        if penalty == 0:
            base = 5.0
        elif penalty <= 2:
            base = _interpolate(penalty, 0, 2, 5.0, 4.0)
        elif penalty <= 5:
            base = _interpolate(penalty, 2, 5, 4.0, 3.0)
        elif penalty <= 8:
            base = _interpolate(penalty, 5, 8, 3.0, 2.0)
        else:
            base = _interpolate(penalty, 8, 15, 2.0, 1.0)

        # 필러 단어 빈도가 높으면 보조 감점 (최대 0.5점)
        # 발화 수 대비 필러 비율로 정규화 (전체 발화의 50% 이상일 때 최대 감점)
        filler_ratio = fillers / total
        filler_penalty = min(0.5, filler_ratio * 0.5)
        return _clamp(base - filler_penalty)

    # ── 발화 완결성 ──
    # 핵심 지표: 미완결 발화 건수
    if criterion == "발화_완결성":
        incomplete = r.get("incomplete_count", 0)
        # 구간: 0~1 → 5점, 2~3 → 4점, 4~5 → 3점, 6~8 → 2점, 9+ → 1점
        if incomplete <= 1:
            return _clamp(_interpolate(incomplete, 0, 1, 5.0, 4.5))
        elif incomplete <= 3:
            return _clamp(_interpolate(incomplete, 1, 3, 4.5, 4.0))
        elif incomplete <= 5:
            return _clamp(_interpolate(incomplete, 3, 5, 4.0, 3.0))
        elif incomplete <= 8:
            return _clamp(_interpolate(incomplete, 5, 8, 3.0, 2.0))
        else:
            return _clamp(_interpolate(incomplete, 8, 14, 2.0, 1.0))

    # ── 언어 일관성 ──
    # LLM 분석: consistency_rate(0~100) 기반
    # 규칙 기반 폴백: mixed_turns 건수 기반 (consistency_rate 오탐 방지)
    if criterion == "언어_일관성":
        method = r.get("method", "rule")
        mixed  = r.get("mixed_turns", 0)

        if method == "llm":
            # LLM 결과: consistency_rate 신뢰 가능
            score = r.get("consistency_rate", 70)
            if score >= 95:
                base = _interpolate(score, 95, 100, 5.0, 5.0)
            elif score >= 85:
                base = _interpolate(score, 85, 95, 4.0, 5.0)
            elif score >= 75:
                base = _interpolate(score, 75, 85, 3.0, 4.0)
            elif score >= 65:
                base = _interpolate(score, 65, 75, 2.0, 3.0)
            else:
                base = _interpolate(score, 0, 65, 1.0, 2.0)
            mixed_penalty = min(1.0, mixed * 0.2)
            return _clamp(base - mixed_penalty)
        else:
            # 규칙 기반 폴백: consistency_rate 오탐 多 → mixed_turns만 사용
            # 구간: 0건 → 5점, 1~2건 → 4점, 3~4건 → 3점, 5~6건 → 2점, 7건+ → 1점
            if mixed == 0:
                return 5.0
            elif mixed <= 2:
                return _clamp(_interpolate(mixed, 0, 2, 5.0, 4.0))
            elif mixed <= 4:
                return _clamp(_interpolate(mixed, 2, 4, 4.0, 3.0))
            elif mixed <= 6:
                return _clamp(_interpolate(mixed, 4, 6, 3.0, 2.0))
            else:
                return _clamp(_interpolate(mixed, 6, 10, 2.0, 1.0))

    # ── 이해 확인 질문 ──
    # 핵심 지표: check_ratio(%) + 전/후반 균등도
    if criterion == "이해_확인_질문":
        check_ratio = r.get("check_ratio", 0)
        first  = r.get("first_half_count", 0)
        second = r.get("second_half_count", 0)
        imbalance = abs(first - second)   # 0이면 완전 균등

        # check_ratio 구간 보간
        # 0~3% → 1~2점, 3~5% → 2~3점, 5~7% → 3~4점, 7~10% → 4~5점, 10%+ → 5점
        if check_ratio >= 10:
            base = _interpolate(check_ratio, 10, 15, 5.0, 5.0)
        elif check_ratio >= 7:
            base = _interpolate(check_ratio, 7, 10, 4.0, 5.0)
        elif check_ratio >= 5:
            base = _interpolate(check_ratio, 5, 7, 3.0, 4.0)
        elif check_ratio >= 3:
            base = _interpolate(check_ratio, 3, 5, 2.0, 3.0)
        else:
            base = _interpolate(check_ratio, 0, 3, 1.0, 2.0)
        # 불균등 패널티: 차이 1당 0.15점, 최대 0.6점
        balance_penalty = min(0.6, imbalance * 0.15)
        return _clamp(base - balance_penalty)

    # ── 참여 유도 ──
    # 핵심 지표: engagement_ratio(%) + student_ratio(%) 복합
    if criterion == "참여_유도":
        eng = r.get("engagement_ratio", 0)
        stu = r.get("student_ratio", 0)
        # 두 지표 각각 보간 후 평균
        if eng >= 15:
            eng_score = _interpolate(eng, 15, 25, 5.0, 5.0)
        elif eng >= 10:
            eng_score = _interpolate(eng, 10, 15, 4.0, 5.0)
        elif eng >= 7:
            eng_score = _interpolate(eng, 7, 10, 3.0, 4.0)
        elif eng >= 5:
            eng_score = _interpolate(eng, 5, 7, 2.0, 3.0)
        else:
            eng_score = _interpolate(eng, 0, 5, 1.0, 2.0)

        if stu >= 20:
            stu_score = _interpolate(stu, 20, 35, 5.0, 5.0)
        elif stu >= 15:
            stu_score = _interpolate(stu, 15, 20, 4.0, 5.0)
        elif stu >= 10:
            stu_score = _interpolate(stu, 10, 15, 3.0, 4.0)
        elif stu >= 5:
            stu_score = _interpolate(stu, 5, 10, 2.0, 3.0)
        else:
            stu_score = _interpolate(stu, 0, 5, 1.0, 2.0)

        # 유도 발화 60% + 학생 반응 40% 가중 평균
        return _clamp(eng_score * 0.6 + stu_score * 0.4)

    # ── 질문 응답 충분성 ──
    # 핵심 지표: answer_rate(%) + insufficient 건수 패널티
    if criterion == "질문_응답_충분성":
        total_q = r.get("total_questions", 0)
        if total_q == 0:
            return 3.0   # 질문 없으면 중립

        answer_rate  = r.get("answer_rate", 0)
        insufficient = len(r.get("insufficient_answers", []))
        unanswered   = len(r.get("unanswered_questions", []))

        # answer_rate 구간 보간
        if answer_rate >= 100:
            base = 5.0
        elif answer_rate >= 90:
            base = _interpolate(answer_rate, 90, 100, 3.0, 5.0)
        elif answer_rate >= 80:
            base = _interpolate(answer_rate, 80, 90, 2.0, 3.0)
        else:
            base = _interpolate(answer_rate, 0, 80, 1.0, 2.0)

        # 미흡 응답 패널티: 1건당 0.3점, 최대 1.5점
        insuff_penalty = min(1.5, insufficient * 0.3)
        # 미응답 패널티: 1건당 0.5점, 최대 2.0점
        unans_penalty  = min(2.0, unanswered * 0.5)
        return _clamp(base - insuff_penalty - unans_penalty)

    # 알 수 없는 지표: raw_score 기반 보간
    raw = r.get("raw_score", 50)
    return _clamp(1.0 + (raw / 100) * 4.0)


RUBRIC_DESCRIPTION = {
    "불필요한_반복_표현": {
        5: "연속 반복 패턴 0건",
        4: "연속 반복 패턴 1~2건",
        3: "연속 반복 패턴 3~5건",
        2: "연속 반복 패턴 6~8건",
        1: "연속 반복 패턴 9건 이상",
    },
    "발화_완결성": {
        5: "미완결 발화 0~1건",
        4: "미완결 발화 2~3건",
        3: "미완결 발화 4~5건",
        2: "미완결 발화 6~8건",
        1: "미완결 발화 9건 이상",
    },
    "언어_일관성": {
        5: "어체 혼용 0건",
        4: "어체 혼용 1~2건",
        3: "어체 혼용 3~4건",
        2: "어체 혼용 5~6건",
        1: "어체 혼용 7건 이상",
    },
    "이해_확인_질문": {
        5: "확인 질문 10% 이상, 전/후반 균등 분포",
        4: "확인 질문 7% 이상, 균등 분포",
        3: "확인 질문 5% 이상",
        2: "확인 질문 3% 이상",
        1: "확인 질문 거의 없음 (3% 미만)",
    },
    "참여_유도": {
        5: "유도 발화 15% 이상, 학생 발화 20% 이상",
        4: "유도 발화 10% 이상, 학생 발화 15% 이상",
        3: "유도 발화 7% 이상, 학생 발화 10% 이상",
        2: "유도 발화 5% 이상, 학생 발화 5% 이상",
        1: "유도 발화 5% 미만, 학생 발화 5% 미만",
    },
    "질문_응답_충분성": {
        5: "응답률 100%, 미흡 0건",
        4: "응답률 100%, 미흡 1건",
        3: "응답률 90% 이상, 미흡 2건 (또는 질문 없음)",
        2: "응답률 80% 이상, 미흡 3건",
        1: "응답률 80% 미만, 미흡 4건 이상",
    },
}

# ─────────────────────────────────────────
# 3. LLM 모델 설정
# ─────────────────────────────────────────
# 지표별로 사용할 Google Gemini 모델을 지정합니다.
# 변경 시 이 딕셔너리만 수정하면 됩니다.
# API 키는 환경변수 GEMINI_API_KEY로 설정하세요.
#
# 사용 가능한 모델:
#   gemini-2.0-flash   → 빠르고 저렴 (단순 판단에 적합)
#   gemini-2.5-flash   → 속도/성능 균형 (중간 추론에 적합)
#   gemini-2.5-pro     → 가장 정교 (복잡한 문맥 분석에 적합)
LLM_MODELS = {
    "불필요한_반복_표현": "gemini-3.1-pro-preview",   # 패턴 감지 → 빠른 모델
    "언어_일관성":        "gemini-3.1-pro-preview",   # 어체 판단 → 빠른 모델로 충분
    "발화_완결성":        "gemini-3.1-pro-preview",   # 의미적 미완결 판단 → 중간 수준
    "이해_확인_질문":     "gemini-3.1-pro-preview",   # 확인 질문 감지 → 빠른 모델
    "참여_유도":          "gemini-3.1-pro-preview",   # 참여 유도 감지 → 빠른 모델
    "질문_응답_충분성":   "gemini-3.1-pro-preview",     # 전체 대화 흐름 추적 → 정교한 모델
}

# ─────────────────────────────────────────
# 3. 패턴 정의
# ─────────────────────────────────────────

# 불필요한 반복 어구 (단독으로 등장하거나 문장 시작 필러)
FILLER_PATTERNS = [
    r"\b이제\s+이제\b",
    r"\b그러니까\s+그러니까\b",
    r"\b뭐\s+뭐\b",
    r"\b그냥\s+그냥\b",
    r"\b이게\s+이게\b",
    r"\b이렇게\s+이렇게\b",
    r"\b그래서\s+그래서\b",
    r"\b예를\s*들어서\s+예를\s*들면\b",
    r"\b예를\s*들어서\s+예를\s*들어서\b",
    r"\b예를\s*들면\s+예를\s*들면\b",
    r"(?<!\w)(이제|그냥|뭐|그러니까|이게|이렇게)(?=\s+\1)",
]

FILLER_SINGLE = [
    "이제", "그냥", "뭐", "그러니까", "사실", "어", "음", "있잖아요",
    "그게", "이게", "근데", "그리고", "또한", "그래서",
]

# 이해 확인 질문 패턴
COMPREHENSION_CHECK_PATTERNS = [
    r"이해\s*(되|하|됐|했)",
    r"아시?겠어요",
    r"알겠어요",
    r"괜찮아요",
    r"이해\s*(되시|하시)",
    r"어렵지\s*않",
    r"(됐나요|됩니까|되죠)",
    r"맞죠\??",
    r"(아시죠|기억하시죠)",
]

# 참여 유도 패턴
ENGAGEMENT_PATTERNS = [
    r"질문\s*(있|해)",
    r"(어떻게|어떤)\s*(생각|의견)",
    r"한번\s*(해봐|봐|생각)",
    r"아시는\s*분",
    r"계세요",
    r"해볼까요",
    r"해봅시다",
    r"같이\s*(해|봐|생각)",
    r"여러분",
]

# 불완전 발화 패턴 (끝이 "..." 이거나 완결어미 없이 끊김)
INCOMPLETE_ENDINGS = [
    r"\.\.\.$",
    r"[,，]\s*$",
    r"(하고|이고|인데|는데|으로|에서|을|를|이|가|은|는)\s*$",
]

# 한국어 완결 어미 패턴
COMPLETE_ENDINGS = [
    r"[다요죠습까]\s*[.?!]?\s*$",
    r"[다요죠습까]\s*$",
]

# ─────────────────────────────────────────
# 3. STT 파싱
# ─────────────────────────────────────────

def parse_stt_file(filepath: str) -> pd.DataFrame:
    """
    STT 텍스트를 DataFrame으로 파싱.
    
    형식: <HH:MM:SS> speaker_id: 발화 내용
    반환: columns = [timestamp, speaker_id, text, speaker_type]
    """
    pattern = re.compile(
        r"<(\d{2}:\d{2}:\d{2})>\s+([a-zA-Z0-9]+):\s+(.+)"
    )
    rows = []

    with open(filepath, encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = pattern.match(line)
        if m:
            ts_str, speaker, text = m.group(1), m.group(2), m.group(3).strip()
            ts = datetime.strptime(ts_str, "%H:%M:%S")
            rows.append({"timestamp": ts, "speaker_id": speaker, "text": text})

    if not rows:
        raise ValueError("파싱된 발화가 없습니다. 파일 형식을 확인하세요.")

    df = pd.DataFrame(rows)

    # 강사 판별: 가장 많이 발화한 화자 = 강사
    instructor_id = df["speaker_id"].value_counts().idxmax()
    df["speaker_type"] = df["speaker_id"].apply(
        lambda x: "instructor" if x == instructor_id else "student"
    )
    df["is_instructor"] = df["speaker_type"] == "instructor"
    return df


def merge_utterances(df: pd.DataFrame,
                     gap_threshold: int = 2) -> pd.DataFrame:
    """
    STT 불완전 전사 처리: 시간 간격 기반 발화 병합.

    같은 화자가 gap_threshold초 이내에 연속 발화한 경우
    한 문장이 여러 줄로 쪼개진 것으로 판단하여 병합합니다.

    처리 규칙:
    - 같은 speaker_id + 시간 간격 ≤ gap_threshold초 → 텍스트 병합
    - 다른 화자가 끼어든 경우 → 병합 중단
    - 원문은 text_raw 컬럼에 보존, 병합 결과는 text 컬럼에 반영
    - 병합된 발화 수는 merged_count 컬럼에 기록

    Args:
        df:            parse_stt_file() 결과 DataFrame
        gap_threshold: 병합 기준 시간 간격 (초, 기본값 2)

    Returns:
        병합된 DataFrame (행 수 감소, 원문 보존)
    """
    df = df.copy()
    df["text_raw"] = df["text"]   # 원문 보존
    rows_list = df.to_dict("records")
    merged = []
    i = 0

    while i < len(rows_list):
        current = rows_list[i].copy()
        current["merged_count"] = 1
        current["merged_texts"] = [current["text"]]

        # 다음 발화와 병합 가능한지 확인
        j = i + 1
        while j < len(rows_list):
            nxt = rows_list[j]

            # 다른 화자가 끼어들면 병합 중단
            if nxt["speaker_id"] != current["speaker_id"]:
                break

            # 시간 간격 계산
            gap = (nxt["timestamp"] - current["timestamp"]).seconds
            if gap > gap_threshold:
                break

            # 병합 실행
            current["merged_texts"].append(nxt["text"])
            current["merged_count"] += 1
            j += 1

        # 병합된 텍스트 조합
        current["text"] = " ".join(current["merged_texts"])
        del current["merged_texts"]
        merged.append(current)
        i = j if j > i + 1 else i + 1

    merged_df = pd.DataFrame(merged)

    total_before = len(df)
    total_after  = len(merged_df)
    reduced      = total_before - total_after
    if reduced > 0:
        print(f"  [전처리] 발화 병합 완료: {total_before}개 → {total_after}개 "
              f"({reduced}개 병합, gap_threshold={gap_threshold}초)")

    return merged_df


# ─────────────────────────────────────────
# 4. 각 지표 분석 함수
# ─────────────────────────────────────────

def analyze_repetition(df: pd.DataFrame) -> dict:
    """
    불필요한 반복 표현 분석 (LLM 기반).
    - 문장 내 연속 중복 어구 감지
    - 필러 어휘 빈도 및 패턴 분석
    - 우회 표현 / 자연스러운 반복 구분
    API 실패 시 규칙 기반 폴백으로 자동 전환.
    """
    import json

    def _default_feedback(penalty_sentences: list, filler_counts: dict) -> dict:
        """LLM이 feedback을 누락했거나 응답이 잘렸을 때 감지된 데이터로 보강."""
        top_fillers = list(dict(sorted(filler_counts.items(), key=lambda x: -x[1])[:3]).keys())
        example_text = penalty_sentences[0]["text"] if penalty_sentences else ""
        if penalty_sentences or filler_counts:
            weakness = f"연속 반복 패턴 {len(penalty_sentences)}건"
            if top_fillers:
                weakness += f", 필러 어휘 '{', '.join(top_fillers)}' 다용"
            suggestion = "같은 단어를 연속으로 반복하지 말고, 필러 어휘 사용을 의식적으로 줄이세요."
            example = (f"원문) {example_text} ▶ 개선) 반복된 표현을 한 번만 말하고 "
                       f"바로 다음 내용으로 이어가세요.") if example_text else ""
        else:
            weakness, suggestion, example = "특별한 약점 없음", "현재 수준을 유지하세요.", ""
        return {"weakness": weakness, "suggestion": suggestion, "example": example}

    inst_df = df[df["is_instructor"]].copy()
    total = len(inst_df)
    if total == 0:
        return {"raw_score": 0, "penalty_count": 0, "method": "empty",
                "total_instructor_turns": 0}

    utterances = [
        f"[{row['timestamp'].strftime('%H:%M:%S')}] {row['text']}"
        for _, row in inst_df.iterrows()
    ]
    utterances_text = "\n".join(utterances)

    prompt = f"""당신은 강의 품질을 분석하는 전문가입니다.
아래는 강사의 발화 목록입니다. 불필요한 반복 표현을 분석해주세요.

[강사 발화]
{utterances_text}

다음을 분석하고, 반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 절대 포함하지 마세요.
중요: JSON 문자열 값 안에서는 작은따옴표(')를 절대 사용하지 마세요. 원문을 인용할 때도 따옴표 없이 그대로 쓰세요.
중요: 아래 JSON의 모든 키(특히 feedback)는 빠짐없이 채워서 응답해야 합니다. feedback을 생략하면 안 됩니다.

분석 항목:
1. penalty_count: 연속 반복 패턴 총 건수 (정수)
2. raw_score: 0~100 사이 정수 (100=반복 없음, 0=매우 심각)
3. summary: 반복 표현에 대한 1~2문장 총평
4. feedback: 강사 개선을 위한 피드백 (반드시 포함)
   - weakness: 이 지표에서 드러난 핵심 약점 (1문장, 감지된 사례가 없으면 "특별한 약점 없음")
   - suggestion: 구체적인 개선 방향 (1~2문장)
   - example: 강사 발화 원문 중 하나를 골라 "원문) ... ▶ 개선) ..." 형식으로,
     실제 원문을 개선 방향에 맞게 다시 쓴 예문 (감지된 사례가 없으면 빈 문자열)
5. penalty_sentences: 연속 반복 패턴이 감지된 발화 목록
   - 같은 단어/어구가 연속으로 반복된 경우 (예: 이제 이제, 그러니까 그러니까)
   - 자연스러운 강조나 의도적 반복은 제외
   - patterns 필드: 반복된 단어를 "연속반복-이제" 형식으로 작성
6. filler_list: 불필요한 필러 어휘 목록 (단어와 빈도를 분리하여 배열로)

[채점 루브릭 - 불필요한 반복 표현]
5점 (score=100): 연속 반복 패턴 0건
4점 (score=80) : 연속 반복 패턴 1~2건
3점 (score=60) : 연속 반복 패턴 3~5건
2점 (score=40) : 연속 반복 패턴 6~8건
1점 (score=20) : 연속 반복 패턴 9건 이상
자연스러운 접속 표현(그래서, 그리고 등)은 패널티에서 제외하세요.

JSON 형식 (이 형식을 정확히 따르고, 모든 키를 빠짐없이 포함하세요):
{{
  "penalty_count": 3,
  "raw_score": 60,
  "summary": "이제의 연속 반복이 3건 감지되었습니다.",
  "feedback": {{
    "weakness": "이제를 연속으로 반복하는 습관이 자주 나타납니다.",
    "suggestion": "같은 어휘를 연속으로 쓰지 말고, 한 번만 말한 뒤 바로 다음 내용으로 넘어가세요.",
    "example": "원문) 이제 이제 오늘은 람다식을 배워볼게요 ▶ 개선) 이제 오늘은 람다식을 배워볼게요"
  }},
  "penalty_sentences": [
    {{"timestamp": "09:08:50", "text": "이제 이제 오늘은...", "patterns": ["연속반복-이제"]}}
  ],
  "filler_list": [
    {{"word": "이제", "count": 7}},
    {{"word": "그냥", "count": 2}}
  ]
}}"""

    try:
        model    = LLM_MODELS.get("불필요한_반복_표현", "gemini-3.1-pro-preview")
        raw_text = _call_gemini(prompt, model, max_tokens=1500)
        llm_result = json.loads(raw_text)

        raw_score     = float(llm_result.get("raw_score", 70))
        penalty_sents = llm_result.get("penalty_sentences", [])
        penalty_count = int(llm_result.get("penalty_count", len(penalty_sents)))

        # filler_list(배열) → filler_word_counts(딕셔너리) 변환
        # Gemini가 배열로 반환하므로 딕셔너리로 정규화
        filler_list   = llm_result.get("filler_list", [])
        filler_counts = {}
        for item in filler_list:
            if isinstance(item, dict):
                word  = str(item.get("word", ""))
                count = int(item.get("count", 0))
                if word:
                    filler_counts[word] = count
            elif isinstance(item, str):
                filler_counts[item] = filler_counts.get(item, 0) + 1

        # 혹시 filler_word_counts 형식으로 반환된 경우도 처리
        if not filler_counts:
            raw_fc = llm_result.get("filler_word_counts", {})
            if isinstance(raw_fc, dict):
                filler_counts = {str(k): int(v) for k, v in raw_fc.items()
                                 if str(v).isdigit() or isinstance(v, int)}

        fb_raw = llm_result.get("feedback", {}) or {}
        feedback = {
            "weakness":   str(fb_raw.get("weakness") or "").strip(),
            "suggestion": str(fb_raw.get("suggestion") or "").strip(),
            "example":    str(fb_raw.get("example") or "").strip(),
        }
        if not (feedback["weakness"] or feedback["suggestion"]):
            # LLM이 feedback을 누락했거나 응답이 중간에 잘린 경우 → 감지된 데이터로 보강
            feedback = _default_feedback(penalty_sents, filler_counts)

        return {
            "raw_score":              round(raw_score, 1),
            "method":                 "llm",
            "penalty_count":          penalty_count,
            "penalty_sentences":      penalty_sents[:5],
            "filler_word_counts":     filler_counts,
            "total_instructor_turns": total,
            "summary":                llm_result.get("summary", ""),
            "feedback":               feedback,
        }

    except Exception as e:
        print(f"  [경고] LLM 질의 실패 (반복 표현: {e}), 규칙 기반으로 폴백합니다.")

        penalty_sentences = []
        for _, row in inst_df.iterrows():
            text = row["text"]
            hits = []
            for pat in FILLER_PATTERNS:
                if re.search(pat, text):
                    hits.append(pat)
            words = text.split()
            for i in range(len(words) - 1):
                if words[i] == words[i + 1] and len(words[i]) > 1:
                    hits.append(f"연속반복: '{words[i]}'")
            if hits:
                penalty_sentences.append({
                    "timestamp": row["timestamp"].strftime("%H:%M:%S"),
                    "text": text,
                    "patterns": hits,
                })

        all_text = " ".join(inst_df["text"].tolist())
        filler_counts = {}
        for fw in FILLER_SINGLE:
            cnt = len(re.findall(rf"\b{fw}\b", all_text))
            if cnt > 0:
                filler_counts[fw] = cnt

        penalty_ratio = len(penalty_sentences) / total
        raw_score = max(0, 100 - penalty_ratio * 200 - sum(filler_counts.values()) * 0.5)

        return {
            "raw_score":            round(raw_score, 1),
            "method":               "fallback",
            "penalty_count":        len(penalty_sentences),
            "penalty_sentences":    penalty_sentences[:5],
            "filler_word_counts":   dict(sorted(filler_counts.items(), key=lambda x: -x[1])[:10]),
            "total_instructor_turns": total,
            "summary":              f"규칙 기반 분석 결과 (LLM 오류: {e})",
            "feedback": _default_feedback(penalty_sentences, filler_counts),
        }


def analyze_utterance_completeness(df: pd.DataFrame) -> dict:
    """
    발화 완결성: Anthropic API를 사용해 의미 단위로 완결성 판단.
    - 어미 완결 여부 (문법적)
    - 의미 완결 여부 (내용이 끊겨 있는지)
    - 설명 도중 흐지부지 끝난 발화 감지
    API 실패 시 규칙 기반 폴백으로 자동 전환.
    """
    import json
    import urllib.request

    def _default_feedback(incomplete_list: list) -> dict:
        """LLM이 feedback을 누락했거나 응답이 잘렸을 때 감지된 데이터로 보강."""
        if incomplete_list:
            example_text = incomplete_list[0].get("text", "")
            weakness = f"미완결 발화 {len(incomplete_list)}건 (어미가 끊기거나 흐지부지 끝남)"
            suggestion = "문장을 끝맺음 어미로 완결한 뒤 다음 내용으로 넘어가세요."
            example = (f"원문) {example_text} ▶ 개선) 핵심 내용을 끝맺음 어미로 마무리해 보세요."
                       if example_text else "")
        else:
            weakness, suggestion, example = "특별한 약점 없음", "현재 수준을 유지하세요.", ""
        return {"weakness": weakness, "suggestion": suggestion, "example": example}

    inst_df = df[df["is_instructor"]].copy()
    total = len(inst_df)
    if total == 0:
        return {"raw_score": 0, "method": "empty"}

    utterances = [
        f"[{row['timestamp'].strftime('%H:%M:%S')}] {row['text']}"
        for _, row in inst_df.iterrows()
    ]
    utterances_text = "\n".join(utterances)

    prompt = f"""당신은 강의 품질을 분석하는 전문가입니다.
아래는 강사의 발화 목록입니다. 발화 완결성 측면에서 분석해주세요.

[강사 발화]
{utterances_text}

다음을 분석하고, 반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 절대 포함하지 마세요.
중요: JSON 문자열 값 안에서는 작은따옴표(')를 절대 사용하지 마세요. 원문을 인용할 때도 따옴표 없이 그대로 쓰세요.
중요: 아래 JSON의 모든 키(특히 feedback)는 빠짐없이 채워서 응답해야 합니다. feedback을 생략하면 안 됩니다.

분석 항목:
1. completeness_score: 발화 완결성 점수 0~100 (100=모든 발화 완결)
2. pattern_summary: 반복되는 불완결 패턴 요약 (없으면 빈 문자열)
3. summary: 발화 완결성에 대한 1~2문장 총평
4. feedback: 강사 개선을 위한 피드백 (반드시 포함)
   - weakness: 이 지표에서 드러난 핵심 약점 (1문장, 없으면 "특별한 약점 없음")
   - suggestion: 구체적인 개선 방향 (1~2문장)
   - example: 미완결 발화 원문 중 하나를 골라 "원문) ... ▶ 개선) ..." 형식으로,
     끝맺음을 완결한 예문 (감지된 사례가 없으면 빈 문자열)
5. incomplete_turns: 불완전한 발화 목록
   - grammatically_incomplete: 어미가 끊긴 문법적 미완결 발화
   - semantically_incomplete: 어미는 있으나 설명이 흐지부지 끝난 의미적 미완결 발화

JSON 형식 (모든 키를 빠짐없이 포함하세요):
{{
  "completeness_score": 85,
  "pattern_summary": "예시를 들다가 마무리 짓지 않는 패턴이 반복됩니다.",
  "summary": "대부분의 발화는 완결되어 있으나 예시 설명 시 미완결 패턴이 관찰됩니다.",
  "feedback": {{
    "weakness": "예시를 들다가 문장을 끝맺지 않고 다음 주제로 넘어가는 경우가 있습니다.",
    "suggestion": "예시를 든 뒤에는 핵심 결론을 한 문장으로 마무리하고 넘어가세요.",
    "example": "원문) 예를 들면 이렇게 보면 ▶ 개선) 예를 들면 이렇게 동작합니다."
  }},
  "incomplete_turns": {{
    "grammatically_incomplete": [
      {{"timestamp": "09:10:10", "text": "...", "reason": "문장이 ~보면 으로 끊김"}}
    ],
    "semantically_incomplete": [
      {{"timestamp": "09:11:00", "text": "...", "reason": "설명 없이 다음 주제로 전환"}}
    ]
  }}
}}

[채점 루브릭 - 발화 완결성]
아래 기준에 따라 completeness_score를 결정하세요.
5점 (score=100): 미완결 발화 0~1건
4점 (score=80) : 미완결 발화 2~3건
3점 (score=60) : 미완결 발화 4~5건
2점 (score=40) : 미완결 발화 6~8건
1점 (score=20) : 미완결 발화 9건 이상
grammatically_incomplete와 semantically_incomplete의 합산 건수를 기준으로 판정하세요."""

    try:
        model    = LLM_MODELS["발화_완결성"]
        raw_text = _call_gemini(prompt, model, max_tokens=1500)
        llm_result = json.loads(raw_text)

        raw_score = float(llm_result.get("completeness_score", 70))
        incomplete_turns = llm_result.get("incomplete_turns", {})
        gram_incomplete  = incomplete_turns.get("grammatically_incomplete", [])
        sem_incomplete   = incomplete_turns.get("semantically_incomplete", [])
        all_incomplete   = gram_incomplete + sem_incomplete

        fb_raw = llm_result.get("feedback", {}) or {}
        feedback = {
            "weakness":   str(fb_raw.get("weakness") or "").strip(),
            "suggestion": str(fb_raw.get("suggestion") or "").strip(),
            "example":    str(fb_raw.get("example") or "").strip(),
        }
        if not (feedback["weakness"] or feedback["suggestion"]):
            feedback = _default_feedback(all_incomplete)

        return {
            "raw_score": round(raw_score, 1),
            "method": "llm",
            "used_model": LLM_MODELS["발화_완결성"],
            "completeness_rate": round(raw_score, 1),
            "incomplete_count": len(all_incomplete),
            "grammatically_incomplete": gram_incomplete,
            "semantically_incomplete": sem_incomplete,
            "incomplete_samples": all_incomplete[:5],
            "pattern_summary": llm_result.get("pattern_summary", ""),
            "summary": llm_result.get("summary", ""),
            "feedback": feedback,
        }

    except Exception as e:
        print(f"  [경고] LLM 질의 실패 (발화 완결성: {e}), 규칙 기반으로 폴백합니다.")

        complete_count = 0
        incomplete_list = []

        for _, row in inst_df.iterrows():
            text = row["text"].strip()
            is_complete   = any(re.search(p, text) for p in COMPLETE_ENDINGS)
            is_incomplete = any(re.search(p, text) for p in INCOMPLETE_ENDINGS)

            if is_complete and not is_incomplete:
                complete_count += 1
            elif is_incomplete:
                incomplete_list.append({
                    "timestamp": row["timestamp"].strftime("%H:%M:%S"),
                    "text": text,
                    "reason": "규칙 기반 감지",
                })
            else:
                complete_count += 0.5

        rate = complete_count / total * 100

        return {
            "raw_score": round(rate, 1),
            "method": "fallback",
            "completeness_rate": round(rate, 1),
            "incomplete_count": len(incomplete_list),
            "grammatically_incomplete": incomplete_list,
            "semantically_incomplete": [],
            "incomplete_samples": incomplete_list[:5],
            "pattern_summary": "",
            "summary": f"규칙 기반 분석 결과 (LLM 오류: {e})",
            "feedback": _default_feedback(incomplete_list),
        }


def analyze_language_consistency(df: pd.DataFrame) -> dict:
    """
    언어 일관성: Anthropic API를 사용해 문맥 기반으로 판단.
    - 존댓말/반말 혼용 (어미 패턴 오탐 없이 의미 단위로 분류)
    - 전문용어 일관성 (같은 개념을 다른 용어로 혼용하는지)
    - 설명 수준 일관성 (갑작스러운 난이도 변화)
    API 실패 시 규칙 기반 폴백으로 자동 전환.
    """
    import json
    import urllib.request

    def _default_feedback(dominant_style: str, mixed_list: list) -> dict:
        """LLM이 feedback을 누락했거나 응답이 잘렸을 때 감지된 데이터로 보강."""
        if mixed_list:
            example_text = mixed_list[0].get("text", "")
            weakness = f"어체 혼용 {len(mixed_list)}건 ('{dominant_style}' 기조에서 다른 어체 등장)"
            suggestion = f"강의 전체에서 '{dominant_style}' 어체로 통일하세요."
            example = (f"원문) {example_text} ▶ 개선) {dominant_style} 어체로 통일하여 표현하세요."
                       if example_text else "")
        else:
            weakness, suggestion, example = "특별한 약점 없음", "현재 수준을 유지하세요.", ""
        return {"weakness": weakness, "suggestion": suggestion, "example": example}

    inst_df = df[df["is_instructor"]].copy()
    total = len(inst_df)
    if total == 0:
        return {"raw_score": 0, "method": "empty"}

    # ── 발화 목록 구성 (타임스탬프 + 텍스트) ──
    utterances = [
        f"[{row['timestamp'].strftime('%H:%M:%S')}] {row['text']}"
        for _, row in inst_df.iterrows()
    ]
    utterances_text = "\n".join(utterances)

    prompt = f"""당신은 강의 품질을 분석하는 전문가입니다.
아래는 강사의 발화 목록입니다. 언어 일관성 측면에서 분석해주세요.

[강사 발화]
{utterances_text}

다음을 분석하고, 반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 절대 포함하지 마세요.
중요: JSON 문자열 값 안에서는 작은따옴표(')를 절대 사용하지 마세요. 원문을 인용할 때도 따옴표 없이 그대로 쓰세요.
중요: 아래 JSON의 모든 키(특히 feedback)는 빠짐없이 채워서 응답해야 합니다. feedback을 생략하면 안 됩니다.

분석 항목:
1. speech_style: 전체적인 어체 (존댓말/반말/혼용 중 하나)
2. consistency_score: 언어 일관성 점수 0~100 (100=완전 일관적)
3. summary: 언어 일관성에 대한 1~2문장 총평
4. feedback: 강사 개선을 위한 피드백 (반드시 포함)
   - weakness: 이 지표에서 드러난 핵심 약점 (1문장, 없으면 "특별한 약점 없음")
   - suggestion: 구체적인 개선 방향 (1~2문장)
   - example: 어체 혼용 또는 용어 혼용 원문 중 하나를 골라 "원문) ... ▶ 개선) ..." 형식으로,
     일관된 어체/용어로 다시 쓴 예문 (감지된 사례가 없으면 빈 문자열)
5. mixed_turns: 어체가 혼용된 발화 목록 (타임스탬프와 이유 포함, 없으면 빈 배열)
6. terminology_issues: 같은 개념을 다른 용어로 혼용한 사례 (없으면 빈 배열)
7. level_issues: 설명 수준이 갑자기 바뀐 사례 (없으면 빈 배열)

JSON 형식 (모든 키를 빠짐없이 포함하세요):
{{
  "speech_style": "존댓말",
  "consistency_score": 85,
  "summary": "전반적으로 존댓말을 유지하나 일부 구간에서 혼용이 발생합니다.",
  "feedback": {{
    "weakness": "존댓말 기조에서 일부 발화가 반말로 전환됩니다.",
    "suggestion": "강의 전체에서 하나의 어체(존댓말)를 끝까지 유지하세요.",
    "example": "원문) 이거 봐봐 ▶ 개선) 이거 보세요"
  }},
  "mixed_turns": [
    {{"timestamp": "09:08:50", "text": "...", "reason": "반말 어미 혼용"}}
  ],
  "terminology_issues": [
    {{"term_a": "스트림", "term_b": "Stream", "context": "같은 개념을 한/영 혼용"}}
  ],
  "level_issues": [
    {{"timestamp": "09:11:00", "text": "...", "reason": "갑자기 고급 개념 등장"}}
  ]
}}

[채점 루브릭 - 언어 일관성]
아래 기준에 따라 consistency_score를 결정하세요.
5점 (score=100): 혼용 0건, 일관성 95% 이상
4점 (score=80) : 혼용 1~2건, 일관성 85% 이상
3점 (score=60) : 혼용 3~4건, 일관성 75% 이상
2점 (score=40) : 혼용 5~6건, 일관성 65% 이상
1점 (score=20) : 혼용 7건 이상, 일관성 65% 미만
mixed_turns 건수와 전체 발화 대비 일관성 비율을 기준으로 판정하세요."""

    try:
        model      = LLM_MODELS["언어_일관성"]
        raw_text   = _call_gemini(prompt, model, max_tokens=1500)
        llm_result = json.loads(raw_text)

        raw_score = float(llm_result.get("consistency_score", 70))

        fb_raw = llm_result.get("feedback", {}) or {}
        feedback = {
            "weakness":   str(fb_raw.get("weakness") or "").strip(),
            "suggestion": str(fb_raw.get("suggestion") or "").strip(),
            "example":    str(fb_raw.get("example") or "").strip(),
        }
        if not (feedback["weakness"] or feedback["suggestion"]):
            feedback = _default_feedback(llm_result.get("speech_style", "존댓말"),
                                          llm_result.get("mixed_turns", []))

        return {
            "raw_score": round(raw_score, 1),
            "method": "llm",
            "used_model": LLM_MODELS["언어_일관성"],
            "dominant_style": llm_result.get("speech_style", "알 수 없음"),
            "consistency_rate": round(raw_score, 1),
            "mixed_turns": len(llm_result.get("mixed_turns", [])),
            "mixed_samples": llm_result.get("mixed_turns", [])[:3],
            "terminology_issues": llm_result.get("terminology_issues", []),
            "level_issues": llm_result.get("level_issues", []),
            "summary": llm_result.get("summary", ""),
            "feedback": feedback,
        }

    except Exception as e:
        # ── 폴백: 규칙 기반 ──
        print(f"  [경고] LLM 질의 실패 ({e}), 규칙 기반으로 폴백합니다.")

        formal_endings  = ["습니다", "합니다", "됩니다", "세요", "어요", "아요", "죠", "네요"]
        informal_endings = ["해", "봐", "거야", "잖아", "거지", "이야", "니까"]

        formal_count, informal_count = 0, 0
        mixed_turns = []

        for _, row in inst_df.iterrows():
            text = row["text"]
            has_formal   = any(text.endswith(e) or f" {e}" in text for e in formal_endings)
            has_informal = any(text.endswith(e) or f" {e}" in text for e in informal_endings)
            if has_formal:   formal_count += 1
            if has_informal: informal_count += 1
            if has_formal and has_informal:
                mixed_turns.append({"timestamp": row["timestamp"].strftime("%H:%M:%S"), "text": text})

        dominant = max(formal_count, informal_count)
        consistency_rate = dominant / total if total > 0 else 0
        raw_score = max(0, min(100, consistency_rate * 100 - len(mixed_turns) * 5))

        dominant_style = "존댓말" if formal_count >= informal_count else "반말"

        return {
            "raw_score": round(raw_score, 1),
            "method": "fallback",
            "dominant_style": dominant_style,
            "consistency_rate": round(consistency_rate * 100, 1),
            "mixed_turns": len(mixed_turns),
            "mixed_samples": mixed_turns[:3],
            "terminology_issues": [],
            "level_issues": [],
            "summary": f"규칙 기반 분석 결과 (LLM 오류: {e})",
            "feedback": _default_feedback(dominant_style, mixed_turns),
        }


def analyze_comprehension_check(df: pd.DataFrame) -> dict:
    """
    이해 확인 질문 분석 (LLM 기반).
    - 명시적 확인 질문 외 우회 표현까지 감지
    - 전/후반 분포 분석
    - 확인 질문의 질적 수준 평가
    API 실패 시 규칙 기반 폴백으로 자동 전환.
    """
    import json

    def _default_feedback(check_ratio_pct: float, sample_text: str) -> dict:
        """LLM이 feedback을 누락했거나 응답이 잘렸을 때 감지된 데이터로 보강."""
        if check_ratio_pct < 5:
            weakness = f"이해 확인 질문 비율이 {check_ratio_pct}%로 낮습니다."
            suggestion = "주요 개념 설명 직후마다 짧게 이해를 확인하는 질문을 덧붙이세요."
            example = (f"원문) {sample_text} ▶ 개선) {sample_text} 여기까지 이해되셨나요?"
                       if sample_text else "")
        else:
            weakness, suggestion, example = "특별한 약점 없음", "현재 수준을 유지하세요.", ""
        return {"weakness": weakness, "suggestion": suggestion, "example": example}

    inst_df = df[df["is_instructor"]].copy()
    total = len(inst_df)
    if total == 0:
        return {"raw_score": 0, "method": "empty"}

    utterances = [
        f"[{row['timestamp'].strftime('%H:%M:%S')}] {row['text']}"
        for _, row in inst_df.iterrows()
    ]
    utterances_text = "\n".join(utterances)

    # 전반/후반 기준 시간
    start = inst_df["timestamp"].min()
    end   = inst_df["timestamp"].max()
    mid   = (start + (end - start) / 2).strftime("%H:%M:%S")

    prompt = f"""당신은 강의 품질을 분석하는 전문가입니다.
아래는 강사의 발화 목록입니다. 학생 이해 확인 질문을 분석해주세요.

[강사 발화]
{utterances_text}

[강의 중간 시점]
{mid} (이전=전반부, 이후=후반부)

다음을 분석하고, 반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 절대 포함하지 마세요.
중요: JSON 문자열 값 안에서는 작은따옴표(')를 절대 사용하지 마세요. 원문을 인용할 때도 따옴표 없이 그대로 쓰세요.
중요: 아래 JSON의 모든 키(특히 feedback)는 빠짐없이 채워서 응답해야 합니다. feedback을 생략하면 안 됩니다.

분석 항목:
1. check_count: 이해 확인 질문 총 횟수
2. check_ratio: 전체 강사 발화 대비 비율 (0~100, 퍼센트)
3. first_half_count: 전반부 확인 질문 횟수
4. second_half_count: 후반부 확인 질문 횟수
5. raw_score: 0~100점
6. summary: 이해 확인 질문에 대한 1~2문장 총평
7. feedback: 강사 개선을 위한 피드백 (반드시 포함)
   - weakness: 이 지표에서 드러난 핵심 약점 (1문장, 양호하면 "특별한 약점 없음")
   - suggestion: 구체적인 개선 방향 (1~2문장)
   - example: 강사 발화 원문 중 하나를 골라 "원문) ... ▶ 개선) ..." 형식으로,
     이해 확인 질문을 덧붙이거나 보강한 예문
8. check_turns: 이해 확인 질문으로 판단된 발화 목록
   - 명시적: "이해되셨나요?", "알겠어요?", "괜찮으세요?"
   - 우회적: "여기까지 따라오고 계세요?", "어렵지 않죠?", "기억하시죠?"
   - 확인 의도가 있는 발화라면 표현 방식과 무관하게 포함

[채점 루브릭 - 이해 확인 질문]
5점 (score=100): 확인 질문 10% 이상, 전/후반 균등 분포
4점 (score=80) : 확인 질문 7% 이상, 균등 분포
3점 (score=60) : 확인 질문 5% 이상
2점 (score=40) : 확인 질문 3% 이상
1점 (score=20) : 확인 질문 거의 없음 (3% 미만)
명시적 표현뿐 아니라 우회적 확인 표현도 포함하세요.

JSON 형식 (모든 키를 빠짐없이 포함하세요):
{{
  "check_count": 4,
  "check_ratio": 13.3,
  "first_half_count": 2,
  "second_half_count": 2,
  "raw_score": 100,
  "summary": "이해 확인 질문이 적절한 빈도로 고르게 분포되어 있습니다.",
  "feedback": {{
    "weakness": "후반부에 이해 확인 질문이 적습니다.",
    "suggestion": "주요 개념 설명이 끝난 직후마다 짧게 이해를 확인하는 질문을 덧붙이세요.",
    "example": "원문) 람다식은 이렇게 씁니다. ▶ 개선) 람다식은 이렇게 씁니다. 여기까지 이해되셨나요?"
  }},
  "check_turns": [
    {{"timestamp": "09:10:30", "text": "여러분 이해되시나요?", "type": "명시적"}},
    {{"timestamp": "09:12:00", "text": "람다식 기억하시죠?", "type": "우회적"}}
  ]
}}"""

    try:
        model      = LLM_MODELS.get("이해_확인_질문", "gemini-3.1-pro-preview")
        raw_text   = _call_gemini(prompt, model, max_tokens=1500)
        llm_result = json.loads(raw_text)

        check_turns  = llm_result.get("check_turns", [])
        check_count  = int(llm_result.get("check_count", len(check_turns)))
        check_ratio  = float(llm_result.get("check_ratio", 0))
        first_half   = int(llm_result.get("first_half_count", 0))
        second_half  = int(llm_result.get("second_half_count", 0))
        raw_score    = float(llm_result.get("raw_score", 70))

        fb_raw = llm_result.get("feedback", {}) or {}
        feedback = {
            "weakness":   str(fb_raw.get("weakness") or "").strip(),
            "suggestion": str(fb_raw.get("suggestion") or "").strip(),
            "example":    str(fb_raw.get("example") or "").strip(),
        }
        if not (feedback["weakness"] or feedback["suggestion"]):
            sample_text = check_turns[0].get("text", "") if check_turns else (
                inst_df["text"].iloc[len(inst_df) // 2] if total > 0 else "")
            feedback = _default_feedback(round(check_ratio, 1), sample_text)

        return {
            "raw_score":          round(raw_score, 1),
            "method":             "llm",
            "check_count":        check_count,
            "check_ratio":        round(check_ratio, 1),
            "first_half_count":   first_half,
            "second_half_count":  second_half,
            "check_samples":      check_turns[:5],
            "summary":            llm_result.get("summary", ""),
            "feedback":           feedback,
        }

    except Exception as e:
        print(f"  [경고] LLM 질의 실패 (이해 확인: {e}), 규칙 기반으로 폴백합니다.")

        check_turns = []
        for _, row in inst_df.iterrows():
            text = row["text"]
            hits = [p for p in COMPREHENSION_CHECK_PATTERNS if re.search(p, text)]
            if hits:
                check_turns.append({
                    "timestamp": row["timestamp"].strftime("%H:%M:%S"),
                    "text": text,
                    "matched_patterns": hits,
                })

        check_count = len(check_turns)
        check_ratio = check_count / total
        if check_ratio < 0.05:
            raw_score = check_ratio / 0.05 * 70
        elif check_ratio <= 0.15:
            raw_score = 70 + (check_ratio - 0.05) / 0.10 * 30
        else:
            raw_score = max(60, 100 - (check_ratio - 0.15) * 200)

        timestamps  = [t["timestamp"] for t in check_turns]
        start       = inst_df["timestamp"].min()
        end         = inst_df["timestamp"].max()
        mid_dt      = start + (end - start) / 2
        first_half  = sum(1 for t_str in timestamps
                          if datetime.strptime(t_str, "%H:%M:%S") <= mid_dt)
        second_half = check_count - first_half

        example_text = inst_df["text"].iloc[len(inst_df) // 2] if total > 0 else ""

        return {
            "raw_score":         round(raw_score, 1),
            "method":            "fallback",
            "check_count":       check_count,
            "check_ratio":       round(check_ratio * 100, 1),
            "first_half_count":  first_half,
            "second_half_count": second_half,
            "check_samples":     check_turns[:5],
            "summary":           f"규칙 기반 분석 결과 (LLM 오류: {e})",
            "feedback": _default_feedback(round(check_ratio * 100, 1), example_text),
        }


def analyze_engagement(df: pd.DataFrame) -> dict:
    """
    참여 유도 분석 (LLM 기반).
    - 명시적 질문 외 참여 유도 의도 발화 감지
    - 실제 학생 반응률과 연계 분석
    - 참여 유도 패턴의 다양성 평가
    API 실패 시 규칙 기반 폴백으로 자동 전환.
    """
    import json

    def _default_feedback(score: float, eng_ratio_pct: float, stu_ratio_pct: float,
                          sample_text: str) -> dict:
        """LLM이 feedback을 누락했거나 응답이 잘렸을 때 감지된 데이터로 보강."""
        if score < 60:
            weakness = (f"참여 유도 발화 {eng_ratio_pct}%, 학생 발화 비율 {stu_ratio_pct}%로 낮습니다.")
            suggestion = "학생에게 직접 질문하거나 답할 시간을 주어 발화 비율을 높이세요."
            example = (f"원문) {sample_text} ▶ 개선) {sample_text} 여러분은 어떻게 생각하세요?"
                       if sample_text else "")
        else:
            weakness, suggestion, example = "특별한 약점 없음", "현재 수준을 유지하세요.", ""
        return {"weakness": weakness, "suggestion": suggestion, "example": example}

    inst_df    = df[df["is_instructor"]].copy()
    student_df = df[~df["is_instructor"]]
    total_inst    = len(inst_df)
    total_student = len(student_df)
    if total_inst == 0:
        return {"raw_score": 0, "method": "empty"}

    # 전체 대화 (강사 + 학생) 구성
    dialogue_lines = [
        f"[{row['timestamp'].strftime('%H:%M:%S')}][{'강사' if row['is_instructor'] else '학생'}] {row['text']}"
        for _, row in df.iterrows()
    ]
    dialogue_text = "\n".join(dialogue_lines)
    student_ratio = round(total_student / len(df) * 100, 1) if len(df) > 0 else 0

    prompt = f"""당신은 강의 품질을 분석하는 전문가입니다.
아래는 강사와 학생의 전체 대화 기록입니다. 학생 참여 유도를 분석해주세요.

[전체 대화]
{dialogue_text}

[참고 수치]
전체 발화 수: {len(df)}건 / 강사: {total_inst}건 / 학생: {total_student}건
학생 발화 비율: {student_ratio}%

다음을 분석하고, 반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 절대 포함하지 마세요.
중요: JSON 문자열 값 안에서는 작은따옴표(')를 절대 사용하지 마세요. 원문을 인용할 때도 따옴표 없이 그대로 쓰세요.
중요: 아래 JSON의 모든 키(특히 feedback)는 빠짐없이 채워서 응답해야 합니다. feedback을 생략하면 안 됩니다.

분석 항목:
1. engagement_count: 참여 유도 발화 총 횟수
2. engagement_ratio: 전체 강사 발화 대비 비율 (0~100, 퍼센트)
3. student_ratio: 전체 발화 중 학생 발화 비율 (0~100, 퍼센트)
4. raw_score: 0~100점
5. summary: 참여 유도에 대한 1~2문장 총평
6. feedback: 강사 개선을 위한 피드백 (반드시 포함)
   - weakness: 이 지표에서 드러난 핵심 약점 (1문장, 양호하면 "특별한 약점 없음")
   - suggestion: 구체적인 개선 방향 (1~2문장)
   - example: 강사 발화 원문 중 하나를 골라 "원문) ... ▶ 개선) ..." 형식으로,
     참여를 유도하는 표현을 덧붙이거나 보강한 예문
7. engagement_turns: 참여 유도로 판단된 강사 발화 목록
   - 명시적: "질문 있으신 분?", "같이 해볼까요?"
   - 우회적: "어떻게 생각하세요?", "한번 생각해보면..."
   - 학생 이름/집단 호명, 실습 유도, 토론 유도 포함

[채점 루브릭 - 참여 유도]
5점 (score=100): 유도 발화 15% 이상, 학생 발화 20% 이상
4점 (score=80) : 유도 발화 10% 이상, 학생 발화 15% 이상
3점 (score=60) : 유도 발화 7% 이상, 학생 발화 10% 이상
2점 (score=40) : 유도 발화 5% 이상, 학생 발화 5% 이상
1점 (score=20) : 유도 발화 5% 미만, 학생 발화 5% 미만
단순 인사말("여러분 안녕하세요")은 참여 유도에서 제외하세요.

JSON 형식 (모든 키를 빠짐없이 포함하세요):
{{
  "engagement_count": 5,
  "engagement_ratio": 16.7,
  "student_ratio": 9.1,
  "raw_score": 60,
  "summary": "참여 유도 빈도는 적절하나 학생 발화 비율이 낮습니다.",
  "feedback": {{
    "weakness": "참여 유도는 적절하나 실제 학생 발화로 이어지는 비율이 낮습니다.",
    "suggestion": "질문 후 답을 바로 이어가지 말고, 학생이 답할 시간을 주고 호명해 보세요.",
    "example": "원문) 코드 한번 봐볼까요. ▶ 개선) 코드 한번 봐볼까요. ○○님, 이 부분 어떻게 동작할 것 같아요?"
  }},
  "engagement_turns": [
    {{"timestamp": "09:09:05", "text": "스트림이 뭔지 아시는 분 계세요?", "type": "명시적"}},
    {{"timestamp": "09:15:00", "text": "코드 한번 봐볼까요.", "type": "우회적"}}
  ]
}}"""

    try:
        model      = LLM_MODELS.get("참여_유도", "gemini-3.1-pro-preview")
        raw_text   = _call_gemini(prompt, model, max_tokens=1500)
        llm_result = json.loads(raw_text)

        eng_turns  = llm_result.get("engagement_turns", [])
        eng_count  = int(llm_result.get("engagement_count", len(eng_turns)))
        eng_ratio  = float(llm_result.get("engagement_ratio", 0))
        stu_ratio  = float(llm_result.get("student_ratio", student_ratio))
        raw_score  = float(llm_result.get("raw_score", 70))

        fb_raw = llm_result.get("feedback", {}) or {}
        feedback = {
            "weakness":   str(fb_raw.get("weakness") or "").strip(),
            "suggestion": str(fb_raw.get("suggestion") or "").strip(),
            "example":    str(fb_raw.get("example") or "").strip(),
        }
        if not (feedback["weakness"] or feedback["suggestion"]):
            sample_text = eng_turns[0].get("text", "") if eng_turns else (
                inst_df["text"].iloc[0] if total_inst > 0 else "")
            feedback = _default_feedback(raw_score, round(eng_ratio, 1), round(stu_ratio, 1), sample_text)

        return {
            "raw_score":         round(raw_score, 1),
            "method":            "llm",
            "engagement_count":  eng_count,
            "engagement_ratio":  round(eng_ratio, 1),
            "student_turns":     total_student,
            "student_ratio":     round(stu_ratio, 1),
            "engagement_samples": eng_turns[:5],
            "summary":           llm_result.get("summary", ""),
            "feedback":          feedback,
        }

    except Exception as e:
        print(f"  [경고] LLM 질의 실패 (참여 유도: {e}), 규칙 기반으로 폴백합니다.")

        engagement_turns = []
        for _, row in inst_df.iterrows():
            text = row["text"]
            hits = [p for p in ENGAGEMENT_PATTERNS if re.search(p, text)]
            if hits:
                engagement_turns.append({
                    "timestamp": row["timestamp"].strftime("%H:%M:%S"),
                    "text": text,
                    "patterns": hits,
                })

        engagement_count = len(engagement_turns)
        engagement_ratio = engagement_count / total_inst
        stu_ratio        = total_student / len(df) if len(df) > 0 else 0
        freq_score       = min(100, engagement_ratio * 400)
        resp_score       = min(100, stu_ratio * 500)
        raw_score        = freq_score * 0.6 + resp_score * 0.4

        example_text = engagement_turns[0]["text"] if engagement_turns else (
            inst_df["text"].iloc[0] if total_inst > 0 else "")

        return {
            "raw_score":          round(raw_score, 1),
            "method":             "fallback",
            "engagement_count":   engagement_count,
            "engagement_ratio":   round(engagement_ratio * 100, 1),
            "student_turns":      total_student,
            "student_ratio":      round(stu_ratio * 100, 1),
            "engagement_samples": engagement_turns[:5],
            "summary":            f"규칙 기반 분석 결과 (LLM 오류: {e})",
            "feedback": _default_feedback(raw_score, round(engagement_ratio * 100, 1),
                                          round(stu_ratio * 100, 1), example_text),
        }


def analyze_response_sufficiency(df: pd.DataFrame) -> dict:
    """
    질문 응답 충분성: Anthropic API를 사용해 Q&A 쌍을 의미론적으로 평가.
    - 질문 감지: 글자 수나 물음표 외에 의문 의도 파악
    - 응답 적절성: 질문의 핵심에 답했는지 여부
    - 미흡 응답: 답했지만 설명이 부족한 경우 감지
    - 미응답: 질문을 흘려보낸 경우 감지
    API 실패 시 규칙 기반 폴백으로 자동 전환.
    """
    import json
    import urllib.request

    def _default_feedback(qa_evals: list, unanswered_list: list, insufficient_list: list) -> dict:
        """LLM이 feedback을 누락했거나 응답이 잘렸을 때 감지된 데이터로 보강."""
        ts_lookup = {qa.get("question_ts"): qa for qa in qa_evals}
        weak_ref = unanswered_list[0] if unanswered_list else (
            insufficient_list[0] if insufficient_list else None)
        if weak_ref:
            qa_match = ts_lookup.get(weak_ref.get("question_ts"), {})
            q_text = qa_match.get("question_text", weak_ref.get("question_text", ""))
            a_text = qa_match.get("answer_text", weak_ref.get("answer_text", ""))
            weakness = f"미응답 {len(unanswered_list)}건, 미흡 응답 {len(insufficient_list)}건이 감지되었습니다."
            suggestion = "학생 질문에 답할 때 구체적인 예시와 근거를 덧붙여 설명을 보강하세요."
            if a_text:
                example = f"원문) {a_text} ▶ 개선) {a_text} 예를 들어 설명을 덧붙이면..."
            elif q_text:
                example = f"원문(미응답)) {q_text} ▶ 개선) 질문에 직접 답한 뒤 다음으로 넘어가세요."
            else:
                example = ""
        else:
            weakness, suggestion, example = "특별한 약점 없음", "현재 수준을 유지하세요.", ""
        return {"weakness": weakness, "suggestion": suggestion, "example": example}

    # 전체 대화 흐름을 타임스탬프와 함께 구성
    rows_list = df.to_dict("records")
    dialogue_lines = []
    for row in rows_list:
        role = "강사" if row["is_instructor"] else "학생"
        ts   = row["timestamp"].strftime("%H:%M:%S")
        dialogue_lines.append(f"[{ts}][{role}] {row['text']}")
    dialogue_text = "\n".join(dialogue_lines)

    prompt = f"""당신은 강의 품질을 분석하는 전문가입니다.
아래는 강사와 학생의 전체 대화 기록입니다. 학생 질문에 대한 강사의 응답 충분성을 분석해주세요.

[전체 대화]
{dialogue_text}

다음을 분석하고, 반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 절대 포함하지 마세요.
중요: JSON 문자열 값 안에서는 작은따옴표(')를 절대 사용하지 마세요. 원문을 인용할 때도 따옴표 없이 그대로 쓰세요.
중요: 아래 JSON의 모든 키(특히 feedback)는 빠짐없이 채워서 응답해야 합니다. feedback을 생략하면 안 됩니다.

분석 항목:
1. sufficiency_score: 응답 충분성 점수 0~100
2. summary: 응답 충분성에 대한 1~2문장 총평
3. feedback: 강사 개선을 위한 피드백 (반드시 포함)
   - weakness: 이 지표에서 드러난 핵심 약점 (1문장, 양호하면 "특별한 약점 없음")
   - suggestion: 구체적인 개선 방향 (1~2문장)
   - example: 미흡하거나 미응답된 답변 원문 중 하나를 골라 "원문) ... ▶ 개선) ..." 형식으로,
     설명을 보강한 예문 (감지된 사례가 없으면 빈 문자열)
4. unanswered_questions: 강사가 응답하지 않은 질문 목록 (없으면 빈 배열)
   각 항목: question_ts, question_text, reason
5. insufficient_answers: 답하긴 했으나 설명이 부족한 사례 (없으면 빈 배열)
   각 항목: question_ts, question_text, answer_text, reason
6. qa_evaluations: 감지된 모든 학생 질문과 강사 응답 평가 목록
   각 항목: question_ts, question_text, answer_ts, answer_text,
            is_answered(bool), quality("충분"/"미흡"/"무응답"), reason

JSON 형식 (모든 키를 빠짐없이 포함하세요):
{{
  "sufficiency_score": 80,
  "summary": "모든 질문에 응답하였으나 일부 답변은 더 상세한 설명이 필요합니다.",
  "feedback": {{
    "weakness": "일부 답변이 단순 확인에 그쳐 구체적인 설명이 부족합니다.",
    "suggestion": "질문에 답할 때 구체적인 예시나 근거를 덧붙여 설명을 보강하세요.",
    "example": "원문) 네 맞습니다. 데이터 처리하는 방식입니다. ▶ 개선) 네 맞습니다. 예를 들어 입력 데이터를 변환한 뒤 저장하는 방식으로 처리합니다."
  }},
  "unanswered_questions": [],
  "insufficient_answers": [
    {{"question_ts": "09:09:15", "question_text": "데이터 처리하는 건가요?",
      "answer_text": "네 맞습니다.", "reason": "단순 확인에 그침, 구체적 예시 없음"}}
  ],
  "qa_evaluations": [
    {{
      "question_ts": "09:09:15",
      "question_text": "데이터 처리하는 건가요?",
      "answer_ts": "09:09:20",
      "answer_text": "네 맞습니다. 데이터 처리하는 방식입니다.",
      "is_answered": true,
      "quality": "미흡",
      "reason": "질문에 간략히만 답하고 구체적인 설명이 없음"
    }}
  ]
}}

[채점 루브릭 - 질문 응답 충분성]
아래 기준에 따라 sufficiency_score를 결정하세요.
5점 (score=100): 응답률 100%, 미흡 0건
4점 (score=80) : 응답률 100%, 미흡 1건
3점 (score=60) : 응답률 90% 이상, 미흡 2건
2점 (score=40) : 응답률 80% 이상, 미흡 3건
1점 (score=20) : 응답률 80% 미만, 미흡 4건 이상
unanswered_questions와 insufficient_answers 건수를 기준으로 판정하세요."""

    try:
        model      = LLM_MODELS["질문_응답_충분성"]
        raw_text   = _call_gemini(prompt, model, max_tokens=3000)
        llm_result = json.loads(raw_text)

        raw_score  = float(llm_result.get("sufficiency_score", 70))
        qa_evals   = llm_result.get("qa_evaluations", [])
        answered   = [q for q in qa_evals if q.get("is_answered")]
        unanswered = llm_result.get("unanswered_questions", [])
        insufficient = llm_result.get("insufficient_answers", [])

        fb_raw = llm_result.get("feedback", {}) or {}
        feedback = {
            "weakness":   str(fb_raw.get("weakness") or "").strip(),
            "suggestion": str(fb_raw.get("suggestion") or "").strip(),
            "example":    str(fb_raw.get("example") or "").strip(),
        }
        if not (feedback["weakness"] or feedback["suggestion"]):
            feedback = _default_feedback(qa_evals, unanswered, insufficient)

        return {
            "raw_score": round(raw_score, 1),
            "method": "llm",
            "used_model": LLM_MODELS["질문_응답_충분성"],
            "total_questions": len(qa_evals),
            "answered_count": len(answered),
            "answer_rate": round(len(answered) / len(qa_evals) * 100, 1) if qa_evals else 100.0,
            "unanswered_questions": unanswered,
            "insufficient_answers": insufficient,
            "qa_evaluations": qa_evals,
            "summary": llm_result.get("summary", ""),
            "feedback": feedback,
        }

    except Exception as e:
        print(f"  [경고] LLM 질의 실패 (응답 충분성: {e}), 규칙 기반으로 폴백합니다.")

        question_pattern = re.compile(r"[?？]|(\b(뭐예요|뭔가요|어떻게|왜|언제|어디서|누가|뭐죠)\b)")
        qa_pairs = []
        rows_list_inner = df.to_dict("records")

        for i, row in enumerate(rows_list_inner):
            if row["speaker_type"] == "student" and question_pattern.search(row["text"]):
                answer_texts = []
                for j in range(i + 1, min(i + 4, len(rows_list_inner))):
                    if rows_list_inner[j]["is_instructor"]:
                        answer_texts.append(rows_list_inner[j]["text"])
                        break
                answer = " ".join(answer_texts) if answer_texts else ""
                qa_pairs.append({
                    "question_ts": row["timestamp"].strftime("%H:%M:%S"),
                    "question_text": row["text"],
                    "answer_text": answer,
                    "is_answered": bool(answer),
                    "quality": "충분" if len(answer) >= 20 else ("미흡" if answer else "무응답"),
                    "reason": "규칙 기반 (글자수 기준)",
                })

        total_q = len(qa_pairs)
        if total_q == 0:
            return {
                "raw_score": 70.0, "method": "fallback",
                "total_questions": 0, "answered_count": 0,
                "answer_rate": 100.0, "unanswered_questions": [],
                "insufficient_answers": [], "qa_evaluations": [],
                "summary": f"학생 질문 없음 (LLM 오류: {e})",
                "feedback": {
                    "weakness": "특별한 약점 없음 (학생 질문 없음)",
                    "suggestion": "현재 수준을 유지하세요.",
                    "example": "",
                },
            }

        answered   = [q for q in qa_pairs if q["is_answered"]]
        answer_rate = len(answered) / total_q
        sufficient  = sum(1 for q in answered if len(q["answer_text"]) >= 20)
        raw_score   = min(100, (answer_rate * 60 + (sufficient / total_q) * 40) * 100)

        insufficient_list = [q for q in answered if len(q["answer_text"]) < 20]
        unanswered_list   = [q for q in qa_pairs if not q["is_answered"]]

        return {
            "raw_score": round(raw_score, 1),
            "method": "fallback",
            "total_questions": total_q,
            "answered_count": len(answered),
            "answer_rate": round(answer_rate * 100, 1),
            "unanswered_questions": unanswered_list,
            "insufficient_answers": insufficient_list,
            "qa_evaluations": qa_pairs,
            "summary": f"규칙 기반 분석 결과 (LLM 오류: {e})",
            "feedback": _default_feedback(qa_pairs, unanswered_list, insufficient_list),
        }


# ─────────────────────────────────────────
# 5. 종합 점수 산출
# ─────────────────────────────────────────

def compute_weighted_score(results: dict) -> pd.DataFrame:
    """
    루브릭 기반 5점 척도로 각 지표를 채점하고 가중점수를 산출합니다.

    채점 방식:
    - _rubric_score()로 지표별 1~5점 결정 (루브릭 기준표 적용)
    - 가중점수 = 루브릭 점수(1~5) × 가중치
    - 종합점수 = 각 지표 가중점수의 합 (최대 5.0점)

    raw_score는 참고용으로만 보존하며 채점에는 사용하지 않습니다.
    """
    rows = []
    weighted_total = 0.0

    for criterion, config in CRITERIA.items():
        weight  = config["weight"]
        result  = results[criterion]
        raw     = result["raw_score"]
        method  = result.get("method", "rule")

        # ── 루브릭 기반 1~5점 채점 ──
        rubric_score = _rubric_score(result, criterion)

        # ── 가중점수 ──
        weighted = round(rubric_score * weight, 3)
        weighted_total += weighted

        # 해당 점수의 루브릭 설명 (소수점 점수 → 가장 가까운 정수 구간으로 매핑)
        rubric_key  = max(1, min(5, round(rubric_score)))
        rubric_desc = RUBRIC_DESCRIPTION.get(criterion, {}).get(rubric_key, "")

        # 분석 방식 레이블
        method_label = {"llm": "LLM", "fallback": "폴백", "rule": "규칙"}.get(method, method)

        rows.append({
            "평가지표":        criterion.replace("_", " "),
            "가중치":          weight,
            "분석방식":        method_label,
            "원점수(100점)":   raw,
            "루브릭점수(5점)": rubric_score,
            "루브릭기준":      rubric_desc,
            "가중점수(5점)":   weighted,
        })

    score_df = pd.DataFrame(rows)
    score_df.loc[len(score_df)] = {
        "평가지표":        "【종합 점수】",
        "가중치":          1.0,
        "분석방식":        "-",
        "원점수(100점)":   "-",
        "루브릭점수(5점)": "-",
        "루브릭기준":      "-",
        "가중점수(5점)":   round(weighted_total, 2),
    }

    return score_df, round(weighted_total, 2)


def get_grade(score: float) -> str:
    """5점 만점 기준 등급"""
    if score >= 4.5: return "S (최우수)"
    if score >= 4.0: return "A (우수)"
    if score >= 3.5: return "B (양호)"
    if score >= 3.0: return "C (보통)"
    if score >= 2.5: return "D (미흡)"
    return "F (개선 필요)"


# ─────────────────────────────────────────
# 6. 리포트 출력
# ─────────────────────────────────────────

SEP = "=" * 65
SEP2 = "-" * 65

def print_report(df: pd.DataFrame, score_df: pd.DataFrame,
                 total_score: float, results: dict,
                 report_json: Optional[dict] = None) -> None:

    inst_id = df[df["is_instructor"]]["speaker_id"].iloc[0]
    inst_turns = df["is_instructor"].sum()
    student_turns = (~df["is_instructor"]).sum()
    duration_sec = (df["timestamp"].max() - df["timestamp"].min()).seconds
    duration_min = duration_sec // 60

    print(f"\n{SEP}")
    print("  강의 품질 분석 리포트")
    print(SEP)
    print(f"  강사 ID       : {inst_id}")
    print(f"  총 발화 수     : {len(df)}건 (강사 {inst_turns} / 학생 {student_turns})")
    print(f"  강의 시간      : 약 {duration_min}분 {duration_sec % 60}초")
    print(f"  종합 점수      : {total_score:.2f} / 5.00점  →  {get_grade(total_score)}")
    print(SEP)

    # ── JSON 항목 요약 ──
    if report_json:
        item_labels = {
            "1.1": ("불필요한_반복_표현", "언어 표현 품질"),
            "1.2": ("발화_완결성",        "언어 표현 품질"),
            "1.3": ("언어_일관성",        "언어 표현 품질"),
            "5.1": ("이해_확인_질문",     "수강생 상호작용"),
            "5.2": ("참여_유도",          "수강생 상호작용"),
            "5.3": ("질문_응답_충분성",   "수강생 상호작용"),
        }
        print(f"\n  파일명   : {report_json.get('file_name', '')}")
        print(f"  날짜     : {report_json.get('date', '') or '(미입력)'}")
        print(f"  강사     : {report_json.get('instructor', '') or '(미입력)'}")
        print(f"  강의 ID  : {report_json.get('course_id', '') or '(미입력)'}")
        print("\n[ 항목별 점수 요약 ]")
        items = report_json.get("items", {})
        last_category = None
        for item_key in sorted(items.keys()):
            item = items[item_key]
            crit_name, category = item_labels.get(item_key, (item_key, ""))
            if category != last_category:
                print(f"  ◆ {category}")
                last_category = category
            print(f"    [{item_key}] {crit_name.replace('_',' '):<14} : {item.get('score', 0)}점")
            print(f"        판정: {item.get('reason', '')[:70]}")
            for ev in item.get("evidence", [])[:2]:
                ts = ev.get("timestamp", "")
                prefix = f"[{ts}] " if ts else ""
                print(f"        근거: {prefix}{ev.get('source', '')[:60]}")
            fb = item.get("feedback", {})
            if fb.get("weakness"):
                print(f"        약점: {fb['weakness'][:70]}")
            if fb.get("suggestion"):
                print(f"        개선: {fb['suggestion'][:70]}")
    print("\n[ Gemini 모델 현황 ]")
    llm_criteria = list(LLM_MODELS.keys())
    for key in llm_criteria:
        model_name = LLM_MODELS.get(key, "(미설정)")
        method = results.get(key, {}).get("method", "unknown")
        status = "✓ LLM 사용" if method == "llm" else "△ 폴백(규칙 기반)"
        print(f"  {key.replace('_',' '):<12} : {model_name:<35} {status}")

    print("\n[ 가중치별 점수 현황 ]")
    print(score_df.to_string(index=False))

    # ── 지표별 상세 인사이트 ──

    print(f"\n{SEP2}")
    print("① 불필요한 반복 표현")
    print(SEP2)
    r = results["불필요한_반복_표현"]
    print(f"  페널티 문장 수 : {r['penalty_count']}건 / {r['total_instructor_turns']}건")
    if r.get("filler_word_counts"):
        top = list(r["filler_word_counts"].items())[:5]
        print(f"  필러 어휘 TOP5 : {', '.join(f'{w}({c}회)' for w, c in top)}")
    if r.get("penalty_sentences"):
        print("  주요 사례:")
        for s in r["penalty_sentences"][:3]:
            print(f"    [{s['timestamp']}] {s['text']}")

    print(f"\n{SEP2}")
    print("② 발화 완결성")
    print(SEP2)
    r = results["발화_완결성"]
    method_label = "LLM 분석" if r.get("method") == "llm" else "규칙 기반(폴백)"
    model_label  = f' ({r["used_model"]})' if r.get("used_model") else ""
    print(f"  분석 방식       : {method_label}{model_label}")
    print(f"  완결성 점수     : {r['completeness_rate']}점")
    print(f"  불완전 발화     : {r['incomplete_count']}건", end="")
    gram = r.get("grammatically_incomplete", [])
    sem  = r.get("semantically_incomplete", [])
    if gram or sem:
        print(f"  (문법적 {len(gram)}건 / 의미적 {len(sem)}건)")
    else:
        print()
    if gram:
        print("  [문법적 미완결]")
        for s in gram[:3]:
            print(f"    [{s.get('timestamp','')}] {s.get('text','')}  → {s.get('reason','')}")
    if sem:
        print("  [의미적 미완결]")
        for s in sem[:3]:
            print(f"    [{s.get('timestamp','')}] {s.get('text','')}  → {s.get('reason','')}")
    if r.get("pattern_summary"):
        print(f"  반복 패턴       : {r['pattern_summary']}")
    if r.get("summary"):
        print(f"  총평            : {r['summary']}")

    print(f"\n{SEP2}")
    print("③ 언어 일관성")
    print(SEP2)
    r = results["언어_일관성"]
    method_label = "LLM 분석" if r.get("method") == "llm" else "규칙 기반(폴백)"
    model_label  = f' ({r["used_model"]})' if r.get("used_model") else ""
    print(f"  분석 방식       : {method_label}{model_label}")
    print(f"  주요 어체       : {r['dominant_style']}")
    print(f"  일관성 점수     : {r['consistency_rate']}점")
    print(f"  어체 혼용 발화  : {r['mixed_turns']}건")
    if r.get("mixed_samples"):
        for s in r["mixed_samples"][:3]:
            ts     = s.get("timestamp", "")
            text   = s.get("text", "")
            reason = s.get("reason", "")
            print(f"    [{ts}] {text}" + (f"  → {reason}" if reason else ""))
    if r.get("terminology_issues"):
        print(f"  용어 혼용 사례  : {len(r['terminology_issues'])}건")
        for t in r["terminology_issues"][:3]:
            print(f"    '{t.get('term_a')}' ↔ '{t.get('term_b')}' : {t.get('context','')}")
    if r.get("level_issues"):
        print(f"  수준 변화 감지  : {len(r['level_issues'])}건")
        for lv in r["level_issues"][:3]:
            print(f"    [{lv.get('timestamp','')}] {lv.get('reason','')}")
    if r.get("summary"):
        print(f"  총평            : {r['summary']}")

    print(f"\n{SEP2}")
    print("④ 이해 확인 질문")
    print(SEP2)
    r = results["이해_확인_질문"]
    print(f"  확인 질문 횟수  : {r['check_count']}회 ({r['check_ratio']}%)")
    print(f"  전반부 / 후반부 : {r['first_half_count']}회 / {r['second_half_count']}회")
    if r.get("check_samples"):
        for s in r["check_samples"][:3]:
            print(f"    [{s['timestamp']}] {s['text']}")

    print(f"\n{SEP2}")
    print("⑤ 참여 유도")
    print(SEP2)
    r = results["참여_유도"]
    print(f"  참여 유도 횟수  : {r['engagement_count']}회 ({r['engagement_ratio']}%)")
    print(f"  학생 발화 비율  : {r['student_ratio']}%")
    if r.get("engagement_samples"):
        for s in r["engagement_samples"][:3]:
            print(f"    [{s['timestamp']}] {s['text']}")

    print(f"\n{SEP2}")
    print("⑥ 질문 응답 충분성")
    print(SEP2)
    r = results["질문_응답_충분성"]
    method_label = "LLM 분석" if r.get("method") == "llm" else "규칙 기반(폴백)"
    model_label  = f' ({r["used_model"]})' if r.get("used_model") else ""
    print(f"  분석 방식       : {method_label}{model_label}")
    print(f"  학생 질문 수    : {r['total_questions']}건")
    print(f"  응답률          : {r['answer_rate']}%")
    if r.get("unanswered_questions"):
        print(f"  미응답 질문     : {len(r['unanswered_questions'])}건")
        for q in r["unanswered_questions"][:2]:
            print(f"    [{q.get('question_ts','')}] {q.get('question_text', q.get('question',''))}")
    if r.get("insufficient_answers"):
        print(f"  미흡한 응답     : {len(r['insufficient_answers'])}건")
        for q in r["insufficient_answers"][:2]:
            print(f"    [{q.get('question_ts','')}] {q.get('reason','')}")
    if r.get("qa_evaluations"):
        print("  Q&A 평가:")
        for qa in r["qa_evaluations"][:3]:
            quality = qa.get("quality", "")
            quality_mark = {"충분": "✓", "미흡": "△", "무응답": "✗"}.get(quality, "?")
            print(f"    {quality_mark} Q [{qa.get('question_ts','')}] {qa.get('question_text', qa.get('question',''))}")
            ans = qa.get("answer_text", qa.get("answer",""))
            if ans:
                print(f"      A  {ans[:60]}...")
            if qa.get("reason"):
                print(f"      → {qa['reason']}")
    if r.get("summary"):
        print(f"  총평            : {r['summary']}")

    # ── 개선 권고 ──
    print(f"\n{SEP}")
    print("  개선 권고사항")
    print(SEP)
    _print_recommendations(results, total_score)
    print(SEP + "\n")


def _print_recommendations(results: dict, total_score: float) -> None:
    """
    루브릭 점수 기반으로 권고사항을 출력합니다.
    권고 기준: 루브릭 점수 3.0점 미만 (보통 이하)
    """
    recs = []

    # ── 불필요한 반복 표현 ──
    r = results["불필요한_반복_표현"]
    rubric = _rubric_score(r, "불필요한_반복_표현")
    if rubric < 3.0:
        penalty = r.get("penalty_count", 0)
        top_fillers = list(r.get("filler_word_counts", {}).keys())[:3]
        msg = f"[반복 표현] 연속 반복 패턴 {penalty}건 감지."
        if top_fillers:
            msg += f" '{', '.join(top_fillers)}' 등 필러 어휘를 의식적으로 줄이세요."
        recs.append(msg)

    # ── 발화 완결성 ──
    r = results["발화_완결성"]
    rubric = _rubric_score(r, "발화_완결성")
    if rubric < 3.0:
        msg = f"[완결성] 불완전 발화 {r.get('incomplete_count', 0)}건 발견. 문장을 끝맺음 어미로 완결 후 다음 내용으로 넘어가세요."
        if r.get("pattern_summary") and r.get("method") == "llm":
            msg += f" 패턴: {r['pattern_summary']}"
        if r.get("summary") and r.get("method") == "llm":
            msg += f" (LLM 총평: {r['summary']})"
        recs.append(msg)

    # ── 언어 일관성 ──
    r = results["언어_일관성"]
    rubric = _rubric_score(r, "언어_일관성")
    if rubric < 3.0:
        mixed = r.get("mixed_turns", 0)
        style = r.get("dominant_style", "존댓말")
        msg = f"[일관성] 어체 혼용 {mixed}건. '{style}' 어체로 통일을 권장합니다."
        if r.get("terminology_issues"):
            msg += f" 용어 혼용 {len(r['terminology_issues'])}건 발견."
        if r.get("summary") and r.get("method") == "llm":
            msg += f" (LLM 총평: {r['summary']})"
        recs.append(msg)

    # ── 이해 확인 질문 ──
    r = results["이해_확인_질문"]
    rubric = _rubric_score(r, "이해_확인_질문")
    if rubric < 3.0:
        if r.get("check_ratio", 0) < 5:
            recs.append("[이해 확인] 학생 이해 확인 빈도가 낮습니다. 10분당 2~3회 확인을 권장합니다.")
        if r.get("first_half_count", 0) > r.get("second_half_count", 0) * 2:
            recs.append("[이해 확인] 후반부 확인 질문이 부족합니다. 전/후반 균등 분포를 권장합니다.")

    # ── 참여 유도 ──
    r = results["참여_유도"]
    rubric = _rubric_score(r, "참여_유도")
    if rubric < 3.0:
        eng = r.get("engagement_ratio", 0)
        stu = r.get("student_ratio", 0)
        msg = f"[참여 유도] 유도 발화 {eng}%, 학생 발화 {stu}%."
        if stu < 10:
            msg += " 질문·토론·실습 요소를 늘려 상호작용을 강화하세요."
        if eng < 7:
            msg += " 학생에게 직접 질문하는 빈도를 높이세요."
        recs.append(msg)

    # ── 질문 응답 충분성 ──
    r = results["질문_응답_충분성"]
    rubric = _rubric_score(r, "질문_응답_충분성")
    if rubric < 3.0 and r.get("total_questions", 0) > 0:
        msg = f"[응답 충분성] 응답률 {r.get('answer_rate', 0)}%. 학생 질문에 충분한 설명을 추가하세요."
        if r.get("unanswered_questions") and r.get("method") == "llm":
            msg += f" 미응답 {len(r['unanswered_questions'])}건 확인 필요."
        if r.get("insufficient_answers") and r.get("method") == "llm":
            msg += f" 미흡 응답 {len(r['insufficient_answers'])}건."
        if r.get("summary") and r.get("method") == "llm":
            msg += f" (LLM 총평: {r['summary']})"
        recs.append(msg)

    if not recs:
        print("  모든 지표가 양호합니다. 현재 수준을 유지하세요.")
    else:
        for i, rec in enumerate(recs, 1):
            print(f"  {i}. {rec}")


# ─────────────────────────────────────────
# 7. JSON 리포트 빌더
# ─────────────────────────────────────────

def build_report_json(filepath: str, df: pd.DataFrame,
                      results: dict, score_df: pd.DataFrame,
                      total_score: float, date: str = "",
                      instructor: str = "", course_id: str = "") -> dict:
    """
    분석 결과를 아래 구조의 JSON으로 정규화.

    {
      "file_name": "...",
      "date": "...",
      "instructor": "...",
      "course_id": "...",
      "items": {
        "1.1": {
          "score": <지표별 루브릭 점수 (1~5)>,
          "reason": "판정 근거",
          "evidence": [{"source": "원문1", "timestamp": "09:08:50"}, ...],
          "feedback": {
            "weakness": "약점",
            "suggestion": "개선 방향",
            "example": "원문에 개선 내용을 적용한 예문"
          }
        },
        "1.2": {...}, "1.3": {...},
        "5.1": {...}, "5.2": {...}, "5.3": {...}
      }
    }

    항목 번호 매핑 (카테고리.순번):
      1.1 = 불필요한_반복_표현   1.2 = 발화_완결성   1.3 = 언어_일관성
      5.1 = 이해_확인_질문       5.2 = 참여_유도     5.3 = 질문_응답_충분성

    date/instructor/course_id는 STT 텍스트만으로는 알 수 없는 외부 메타데이터이므로
    main()의 --date/--instructor/--course-id 인자로 전달받습니다.
    instructor를 입력하지 않으면 STT에서 감지된 강사 화자 ID를 사용합니다.
    """
    import os

    file_name = os.path.basename(filepath)

    # score_df에서 지표별 루브릭 점수 추출 (종합 점수 행 제외)
    score_map = {
        row["평가지표"].replace(" ", "_"): {
            "weighted_score": row["가중점수(5점)"],
            "rubric_score":   row["루브릭점수(5점)"],
            "rubric_desc":    row["루브릭기준"],
        }
        for _, row in score_df.iterrows()
        if row["평가지표"] != "【종합 점수】"
    }

    def _wrap_evidence(items: list) -> list:
        """(원문, 타임스탬프) 튜플 목록을 [{"source": "...", "timestamp": "..."}] 형태로 변환."""
        return [{"source": text, "timestamp": ts} for text, ts in items]

    def _feedback_of(r: dict) -> dict:
        fb = r.get("feedback") or {}
        return {
            "weakness":   fb.get("weakness", ""),
            "suggestion": fb.get("suggestion", ""),
            "example":    fb.get("example", ""),
        }

    # ── 카테고리 1: 언어 표현 품질 ──
    def _evidence_repetition(r: dict) -> list:
        ev = [(s["text"], s.get("timestamp", "")) for s in r.get("penalty_sentences", [])]
        top_fillers = [f"{w}({c}회)" for w, c in list(r.get("filler_word_counts", {}).items())[:3]]
        if top_fillers:
            ev.append(("필러 어휘: " + ", ".join(top_fillers), ""))
        return ev or [("감지된 사례 없음", "")]

    def _reason_repetition(r: dict) -> str:
        cnt = r.get("penalty_count", 0)
        total = r.get("total_instructor_turns", 1)
        top = list(r.get("filler_word_counts", {}).keys())[:3]
        base = f"페널티 발화 {cnt}/{total}건"
        return base + (f", 주요 필러: {', '.join(top)}" if top else "")

    def _evidence_completeness(r: dict) -> list:
        # 문법적 미완결 대표 1개, 의미적 미완결 대표 1개만 추출
        gram = r.get("grammatically_incomplete", [])
        sem  = r.get("semantically_incomplete", [])
        ev   = []
        if gram:
            ev.append((gram[0].get("text", ""), gram[0].get("timestamp", "")))
        if sem:
            ev.append((sem[0].get("text", ""), sem[0].get("timestamp", "")))
        return ev or [("감지된 사례 없음", "")]

    def _reason_completeness(r: dict) -> str:
        gram_cnt = len(r.get("grammatically_incomplete", []))
        sem_cnt  = len(r.get("semantically_incomplete", []))
        total    = r.get("incomplete_count", 0)
        base     = f"총 {total}건 감지 (문법적 {gram_cnt}건, 의미적 {sem_cnt}건)"
        if r.get("pattern_summary"):
            base += f". {r['pattern_summary']}"
        elif r.get("summary"):
            base += f". {r['summary']}"
        return base

    def _evidence_consistency(r: dict) -> list:
        ev = [(f"[어체혼용] {s.get('text','')}", s.get('timestamp', '')) for s in r.get("mixed_samples", [])]
        ev += [(f"[용어혼용] '{t.get('term_a')}' ↔ '{t.get('term_b')}'", "")
               for t in r.get("terminology_issues", [])]
        ev += [(f"[수준변화] {lv.get('reason','')}", lv.get('timestamp', '')) for lv in r.get("level_issues", [])]
        return ev or [("감지된 사례 없음", "")]

    def _reason_consistency(r: dict) -> str:
        if r.get("summary"):
            return r["summary"]
        return f"어체 혼용 {r.get('mixed_turns', 0)}건, 일관성 {r.get('consistency_rate', 0)}점"

    # ── 카테고리 5: 수강생 상호작용 ──
    def _evidence_comprehension(r: dict) -> list:
        ev = [(s["text"], s.get("timestamp", "")) for s in r.get("check_samples", [])]
        return ev or [("이해 확인 질문 없음", "")]

    def _reason_comprehension(r: dict) -> str:
        return (f"확인 질문 {r.get('check_count', 0)}회 ({r.get('check_ratio', 0)}%), "
                f"전반 {r.get('first_half_count', 0)}회 / 후반 {r.get('second_half_count', 0)}회")

    def _evidence_engagement(r: dict) -> list:
        ev = [(s["text"], s.get("timestamp", "")) for s in r.get("engagement_samples", [])]
        return ev or [("참여 유도 발화 없음", "")]

    def _reason_engagement(r: dict) -> str:
        return (f"참여 유도 {r.get('engagement_count', 0)}회 ({r.get('engagement_ratio', 0)}%), "
                f"학생 발화 비율 {r.get('student_ratio', 0)}%")

    def _evidence_sufficiency(r: dict) -> list:
        ev = []
        for qa in r.get("qa_evaluations", []):
            q_text = qa.get("question_text", qa.get("question", ""))
            quality = qa.get("quality", "")
            ts = qa.get("question_ts", "")
            ev.append((f"[{quality}] Q: {q_text}", ts))
        return ev or [("학생 질문 없음", "")]

    def _reason_sufficiency(r: dict) -> str:
        if r.get("summary"):
            return r["summary"]
        return (f"응답률 {r.get('answer_rate', 0)}%, "
                f"미응답 {len(r.get('unanswered_questions', []))}건, "
                f"미흡 {len(r.get('insufficient_answers', []))}건")

    # ── 결과 dict 모음 ──
    r_rep  = results["불필요한_반복_표현"]
    r_com  = results["발화_완결성"]
    r_con  = results["언어_일관성"]
    r_chk  = results["이해_확인_질문"]
    r_eng  = results["참여_유도"]
    r_suf  = results["질문_응답_충분성"]

    def _build_item(criterion: str, r: dict, evidence_fn, reason_fn) -> dict:
        raw_score = score_map.get(criterion, {}).get("rubric_score", 0)
        score = max(1, min(5, round(raw_score)))  # 개별 지표 점수는 정수(1의 자리)로 표시
        feedback = _feedback_of(r)
        if score >= 5:
            feedback["example"] = "해당 사항 없음"
        return {
            "score":    score,
            "reason":   reason_fn(r),
            "evidence": _wrap_evidence(evidence_fn(r)),
            "feedback": feedback,
        }

    items = {
        "1.1": _build_item("불필요한_반복_표현", r_rep, _evidence_repetition,    _reason_repetition),
        "1.2": _build_item("발화_완결성",        r_com, _evidence_completeness, _reason_completeness),
        "1.3": _build_item("언어_일관성",        r_con, _evidence_consistency,  _reason_consistency),
        "5.1": _build_item("이해_확인_질문",     r_chk, _evidence_comprehension, _reason_comprehension),
        "5.2": _build_item("참여_유도",          r_eng, _evidence_engagement,    _reason_engagement),
        "5.3": _build_item("질문_응답_충분성",   r_suf, _evidence_sufficiency,   _reason_sufficiency),
    }

    # instructor 미입력 시 STT에서 감지된 강사 화자 ID로 대체
    if not instructor:
        inst_rows = df[df["is_instructor"]]
        instructor = inst_rows["speaker_id"].iloc[0] if len(inst_rows) > 0 else ""

    report = {
        "file_name":  file_name,
        "date":       date,
        "instructor": instructor,
        "course_id":  course_id,
        "items":      items,
    }

    return report


# ─────────────────────────────────────────
# 8. 엔트리포인트
# ─────────────────────────────────────────
def run_batch(filepaths: list, model_overrides: Optional[dict] = None,
             gap_threshold: int = 2, date: str = "", instructor: str = "",
             course_id: str = "") -> dict:
    """
    여러 STT 파일을 순회하며 개별 분석합니다.
    파일명은 YYYY-MM-DD_로 시작해야 하며, 날짜순으로 정렬 후 처리합니다.

    Returns:
        {파일명: (df, results, score_df, total_score, report_json), ...}
        날짜 패턴이 맞지 않는 파일은 건너뛰고 경고 출력.
    """
    import os

    date_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})_")
    valid_files  = []

    for fp in filepaths:
        basename = os.path.basename(fp)
        m = date_pattern.match(basename)
        if not m:
            print(f"  [건너뜀] 파일명이 YYYY-MM-DD_ 형식이 아닙니다: {basename}")
            continue
        valid_files.append((m.group(1), fp))

    if not valid_files:
        print("  [오류] 처리 가능한 파일이 없습니다. 파일명을 확인하세요.")
        return {}

    # 날짜순 정렬
    valid_files.sort(key=lambda x: x[0])

    print(f"\n{'='*65}")
    print(f"  일괄 분석 시작: 총 {len(valid_files)}개 파일")
    print(f"{'='*65}")
    for date_str, fp in valid_files:
        print(f"    - {date_str} : {os.path.basename(fp)}")

    batch_results = {}
    for idx, (date_str, fp) in enumerate(valid_files, 1):
        print(f"\n{'#'*65}")
        print(f"  [{idx}/{len(valid_files)}] {date_str} 강의 분석 중...")
        print(f"{'#'*65}")
        try:
            result = main(fp, model_overrides=model_overrides, gap_threshold=gap_threshold,
                                     date=date, instructor=instructor, course_id=course_id)
            batch_results[os.path.basename(fp)] = result
        except Exception as e:
            print(f"  [오류] {fp} 처리 중 예외 발생: {e}")
            continue

    print(f"\n{'='*65}")
    print(f"  일괄 분석 완료: {len(batch_results)}/{len(valid_files)}개 성공")
    print(f"{'='*65}\n")

    return batch_results


def main(filepath: str, model_overrides: Optional[dict] = None,
         gap_threshold: int = 2, date: str = "", instructor: str = "",
         course_id: str = ""):
    """
    model_overrides 예시:
        {
            "언어_일관성":      "claude-opus-4-6",
            "발화_완결성":      "claude-haiku-4-5-20251001",
            "질문_응답_충분성": "claude-sonnet-4-6",
        }
    None이면 LLM_MODELS 기본값 사용.
    gap_threshold: 발화 병합 기준 시간 간격 (초, 기본값 2)
    date/instructor/course_id: STT 파일만으로는 알 수 없는 메타데이터.
        instructor를 비워두면 STT에서 감지된 강사 화자 ID를 사용합니다.
    """
    # 런타임 모델 오버라이드 적용
    if model_overrides:
        for key, model in model_overrides.items():
            if key in LLM_MODELS:
                LLM_MODELS[key] = model
                print(f"  [모델 변경] {key} → {model}")
            else:
                print(f"  [경고] 알 수 없는 지표 키: {key} (무시됨)")

    print(f"\n  파일 로드 중: {filepath}")
    df = parse_stt_file(filepath)
    print(f"  파싱 완료: 총 {len(df)}개 발화")

    # ── 전처리: 불완전 전사 병합 ──
    df = merge_utterances(df, gap_threshold=gap_threshold)
    print(f"  전처리 후: 총 {len(df)}개 발화")

    print("  분석 중...")
    print(f"  사용 모델: " + " | ".join(
        f"{k.replace('_',' ')}={v}" for k, v in LLM_MODELS.items()
    ))
    results = {
        "불필요한_반복_표현": analyze_repetition(df),
        "발화_완결성":        analyze_utterance_completeness(df),
        "언어_일관성":        analyze_language_consistency(df),
        "이해_확인_질문":     analyze_comprehension_check(df),
        "참여_유도":          analyze_engagement(df),
        "질문_응답_충분성":   analyze_response_sufficiency(df),
    }

    score_df, total_score = compute_weighted_score(results)

    # JSON 빌드 → 저장
    import json as _json
    report_json = build_report_json(filepath, df, results, score_df, total_score,
                                     date=date, instructor=instructor, course_id=course_id)
    out_json = filepath.replace(".txt", "_report.json")
    with open(out_json, "w", encoding="utf-8") as f:
        _json.dump(report_json, f, ensure_ascii=False, indent=2)
    print(f"  JSON 저장 완료: {out_json}")

    # 리포트 출력 (JSON 기반)
    print_report(df, score_df, total_score, results, report_json)

    # CSV 저장
    out_csv = filepath.replace(".txt", "_score_report.csv")
    score_df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"  점수 표 저장 완료: {out_csv}")

    return df, results, score_df, total_score, report_json


# 사용 가능한 Anthropic 모델 목록 (CLI 검증용)
AVAILABLE_MODELS = [
    "gemini-2.0-flash",
    "gemini-3.1-pro-preview",
    "gemini-3.1-pro-preview",
]

# LLM이 적용되는 지표 키 목록 (CLI 검증용)
LLM_CRITERIA_KEYS = list(LLM_MODELS.keys())


if __name__ == "__main__":
    # ── server.js spawn 연동: python lecture_analyzer.py <txt경로> ──
    # argparse보다 먼저 체크해야 unrecognized arguments 오류 방지
    if len(sys.argv) == 2 and sys.argv[1].endswith(".txt") and not sys.argv[1].startswith("-"):
        import json as _json
        from pathlib import Path as _Path
        # 이중 이스케이프 및 경로 정규화
        txt_path = str(_Path(sys.argv[1]).resolve())
        try:
            _, _, _, _, report = main(filepath=txt_path)
            print(_json.dumps(report, ensure_ascii=False))
        except Exception as e:
            print(_json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(0)

    parser = argparse.ArgumentParser(
        description="강의 STT 품질 분석기",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--file",
        default="",
        help="STT 텍스트 파일 경로",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        default=[
        "",
        ],
        help=(
            "여러 STT 파일을 한 번에 분석 (파일별 개별 리포트 생성)\n"
            "  파일명은 YYYY-MM-DD_로 시작해야 함 (예: 2026-02-02_자바.txt)\n"
            "  예시: --files 2026-02-02_자바.txt 2026-02-03_자바.txt"
        ),
    )
    parser.add_argument(
        "--model",
        action="append",
        metavar="지표=모델명",
        help=(
            "지표별 모델 오버라이드 (여러 번 사용 가능)\n"
            f"  지표 키: {', '.join(LLM_CRITERIA_KEYS)}\n"
            f"  모델명: {', '.join(AVAILABLE_MODELS)}\n"
            "  예시: --model 언어_일관성=claude-opus-4-6\n"
            "        --model 발화_완결성=claude-haiku-4-5-20251001"
        ),
    )
    parser.add_argument(
        "--gap",
        type=int,
        default=2,
        metavar="초",
        help=(
            "발화 병합 기준 시간 간격 (초, 기본값 2)\n"
            "  같은 화자가 N초 이내 연속 발화하면 한 문장으로 병합\n"
            "  예시: --gap 1  (보수적, 확실한 분절만 병합)\n"
            "        --gap 2  (권장, STT 분절 오류 대부분 커버)\n"
            "        --gap 3  (공격적, 자연스러운 pause도 병합)"
        ),
    )
    parser.add_argument(
        "--date",
        default="2026-02-04",
        metavar="YYYY-MM-DD",
        help="강의 날짜 (STT 파일만으로는 알 수 없어 직접 입력, 미입력시 빈 값)",
    )
    parser.add_argument(
        "--instructor",
        default="오현수",
        help="강사명 (미입력시 STT에서 감지된 강사 화자 ID 사용)",
    )
    parser.add_argument(
        "--course-id",
        dest="course_id",
        default="kdt-web-3th",
        help="강의(코스) ID (미입력시 빈 값)",
    )
    args = parser.parse_args()

    # --model 파싱 및 검증
    overrides = {}
    if args.model:
        for entry in args.model:
            if "=" not in entry:
                parser.error(f"--model 형식 오류: '{entry}' → '지표=모델명' 형식으로 입력하세요.")
            key, model_name = entry.split("=", 1)
            if key not in LLM_CRITERIA_KEYS:
                parser.error(f"알 수 없는 지표 키: '{key}'\n사용 가능: {', '.join(LLM_CRITERIA_KEYS)}")
            if model_name not in AVAILABLE_MODELS:
                print(f"  [경고] 미검증 모델명: '{model_name}' — 그대로 사용합니다.")
            overrides[key] = model_name

    if args.files:
        run_batch(args.files, model_overrides=overrides or None, gap_threshold=args.gap,
         date=args.date, instructor=args.instructor, course_id=args.course_id)
    else:
        main(args.file, model_overrides=overrides or None, gap_threshold=args.gap,
         date=args.date, instructor=args.instructor, course_id=args.course_id)