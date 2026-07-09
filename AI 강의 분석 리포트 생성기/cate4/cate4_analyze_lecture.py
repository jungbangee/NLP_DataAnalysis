"""
Gemini API를 사용하는 강의 분석 스크립트

사전 준비:
  pip install google-generativeai rapidfuzz
  Gemini API 키: https://aistudio.google.com
"""
import os
import re
import json
from pathlib import Path
from typing import Optional, Tuple, List  # Python 3.9 호환 타입 힌트

from google import genai
from google.genai import types as genai_types

# rapidfuzz 설치: pip install rapidfuzz
try:
    from rapidfuzz import fuzz as _fuzz
    _FUZZY_AVAILABLE = True
except ImportError:
    _FUZZY_AVAILABLE = False

# ── Gemini API 설정 ──────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyB-ZoAe_gLepBQMoqBxHipAu6Qqyg-bP6U")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")

# 데이터 디렉터리 설정
BASE_DIR = Path(__file__).parent / "NLP 과제 1 - AI 강의 분석 리포트 생성기" / "NLP 과제 1 - AI 강의 분석 리포트 생성기"
LECTURE_SCRIPT_DIR = BASE_DIR / "강의 스크립트"

# JSON 저장 경로: 프로젝트 루트의 json 폴더
OUTPUT_DIR = Path(__file__).parent / "json"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_gemini_model(api_key: Optional[str] = None, model_name: Optional[str] = None) -> Tuple[genai.Client, str]:
    """Gemini 클라이언트와 모델명을 반환합니다."""
    key = api_key or GEMINI_API_KEY
    mdl = model_name or GEMINI_MODEL

    if not key or key == "your-api-key":
        raise ValueError(
            "Gemini API 키가 설정되지 않았습니다. "
            "파일 상단 GEMINI_API_KEY를 수정하거나 환경 변수 GEMINI_API_KEY를 설정하세요.\n"
            "API 키 발급: https://aistudio.google.com"
        )

    client = genai.Client(api_key=key)
    return client, mdl


DEFAULT_PROMPT = """
# Role
너는 강의 품질 평가 체크리스트(ver. 2.0, 백엔드 부트캠프 21기: Java)를 기반으로
IT/실무 교육 과정의 강의를 심사하는 전문 평가 위원이다.
제공된 강의 스크립트를 바탕으로 아래 평가 기준 4. 예시 및 실습 연계 의 세 항목을 객관적으로 평가하라.

평가 기준 원문:
- 4.1 예시 적절성  : "예시가 강의 수준 및 실제 업무 현장과 연관성이 있는가" (가중치: 높음)
- 4.2 실습 연계    : "이론 설명 후 실습으로 자연스럽게 연결되는가" (가중치: 높음)
- 4.3 오류 대응    : "실습 중 발생하는 오류나 질문에 적절히 대응하는가" (가중치: 중간)

점수 기준: 5점(매우 우수) / 4점(우수) / 3점(보통) / 2점(미흡) / 1점(매우 미흡) / 0점(N/A, 해당 없음·평가 불가)

# Theoretical Background
1. 메릴(Merrill)의 'First Principles of Instruction': 이론이 실제 과제 해결 및 현업으로 유기적으로 연결되는가
2. 조나센(Jonassen)의 'Troubleshooting Theory': 오류 발생 시 단순 해결책을 넘어 구조적 원인을 인지적으로 스캐폴딩하는가
3. 앤드라고지(Andragogy) 실무 연계성 원리: 학습 내용이 성인 학습자의 실제 직무 환경과 일치하는가

# Evaluation Criteria

## 4.1 예시 적절성 (Example Relevance & Authenticity)
세부 기준: 예시가 강의 수준 및 실제 업무 현장과 연관성이 있는가

### 원문 추출 기준
- "예를 들어", "예컨대", "실제로", "현업에서", "실무에서" 등 명시적 예시 도입 표현이 있거나
  구체적 시나리오가 독립적으로 제시된 문장만 선택
- 강사가 개념 설명 중 쓰는 비유적 표현, 단순 화면 설명은 제외
- 조건을 만족하는 문장이 없으면 evidence를 빈 배열([])로 반환

### 점수 척도
0(N/A): 스크립트가 너무 짧거나 예시 적절성을 판단할 내용이 없음
1(매우 미흡): 예시가 전혀 없거나 실무와 완전히 동떨어진 인위적 상황만 제시
2(미흡): 예시가 존재하나 지나치게 단순·추상적이어서 실무 적용 가능성이 낮음
3(보통): 이론과 예시 주제는 일치하나 Toy Project 수준의 단순화된 형태에 그침
4(우수): 실무 맥락을 충분히 반영하며 학습자가 현업과의 연결을 쉽게 인식할 수 있음
5(매우 우수): 현업 복잡성과 도메인 특성을 완벽히 반영하며 즉시 투입 가능한 시나리오로 구성됨

---

## 4.2 실습 연계 (Theory-to-Practice Integration)
세부 기준: 이론 설명 후 실습으로 자연스럽게 연결되는가

### 원문 추출 기준
- 행위 주체가 반드시 수강생이어야 함: "여러분이 직접", "해보세요", "따라해보시면", "이제 여러분 차례"
- 수강생에게 독립적 수행을 명시적으로 요청하는 맥락 (과제 부여, 실습 시작 안내 등)
- 강사의 시연 예고("제가 해보겠습니다")나 이론 설명 중 동사 사용은 제외
- 조건을 만족하는 문장이 없으면 evidence를 빈 배열([])로 반환

### 점수 척도
0(N/A): 스크립트가 너무 짧거나 이론/실습 구분 자체가 불가능한 내용
1(매우 미흡): 이론 설명과 실습이 완전히 분절됨, 브릿지(Bridge)가 전혀 없음
2(미흡): 이론과 실습의 주제가 느슨하게 연결되나 전환 시점에 아무런 안내 없이 실습 시작
3(보통): 이론과 실습의 주제는 일치하나 이론에서 강조한 핵심 개념의 연결 설명(Why & How)이 부족
4(우수): 이론과 실습의 연결이 대체로 자연스러우나 일부 개념이 실습에 반영되지 않거나 전환 설명이 간략히 생략됨
5(매우 우수): 이론 설명과 실습 과제가 완벽히 일치하며 학습자의 인지 부하를 최소화하는 매끄러운 브릿지가 설계됨

---

## 4.3 오류 대응 (Instructional Troubleshooting & Scaffolding)
세부 기준: 실습 중 발생하는 오류나 질문에 적절히 대응하는가

### 원문 추출 기준
- 실제 오류/예외 상황이 명시적으로 언급되어야 함
  (에러 메시지 직접 언급, "안 되시는 분", "오류가 나면", "에러가 뜨면" 등)
- 오류 언급 직후 강사의 대응 발화(원인 설명, 해결 안내, 경고)가 이어져야 함
- 추상적으로 "문제가 있다", "이슈가 있다" 수준의 표현은 제외
- 조건을 만족하는 문장이 없으면 evidence를 빈 배열([])로 반환

### 점수 척도
0(N/A): 스크립트가 너무 짧거나 실습 구간 자체가 없어 오류 대응 여부 판단 불가
1(매우 미흡): 오류/예외 상황에 대한 안내가 전혀 없음
2(미흡): 오류 발생 가능성을 인지하나 "그냥 넘어가세요", "무시하세요" 수준의 소극적 대응에 그침
3(보통): 오류 해결 방법은 명확히 제시하나 왜 그런 에러가 발생했는지 원인 설명이 생략됨
4(우수): 오류 원인 설명이 포함되어 있으나 학습자 스스로 추론하도록 유도하는 스캐폴딩이 부족함
5(매우 우수): 발생 가능한 오류를 선제적으로 경고하거나 디버깅 경로(원인 분석 → 추론 → 해결)를 논리적으로 안내함

# Output Format
반드시 아래 JSON 포맷으로만 출력하라.
JSON 앞뒤에 ```json 또는 ``` 같은 마크다운 코드 블록 기호를 절대 포함하지 마라.
JSON 외의 어떠한 텍스트, 설명, 주석도 포함하지 마라.
점수는 정수(0~5)로만 표기하라.
evidence는 스크립트에서 그대로 복사한 문장 배열이며, 없으면 빈 배열([])을 반환하라.

feedback 작성 규칙:
- weakness  : 이 강의에서 해당 항목의 구체적인 부족한 점을 1~2문장으로 기술하라. 점수가 5점이면 "해당 사항 없음"으로 작성하라.
- suggestion: weakness를 개선하기 위한 구체적이고 실행 가능한 방법을 1~2문장으로 기술하라. 점수가 5점이면 "현재 수준을 유지하세요."로 작성하라.
- example   : suggestion을 이 강의의 실제 주제와 내용에 맞게 적용한 구체적인 예시 문장을 작성하라. evidence가 없거나 점수가 5점이면 "해당 사항 없음"으로 작성하라.

{
  "items": {
    "4.1": {
      "score": 0,
      "reason": "",
      "evidence": [],
      "feedback": {
        "weakness": "",
        "suggestion": "",
        "example": ""
      }
    },
    "4.2": {
      "score": 0,
      "reason": "",
      "evidence": [],
      "feedback": {
        "weakness": "",
        "suggestion": "",
        "example": ""
      }
    },
    "4.3": {
      "score": 0,
      "reason": "",
      "evidence": [],
      "feedback": {
        "weakness": "",
        "suggestion": "",
        "example": ""
      }
    }
  }
}
"""


def index_script(raw_text: str) -> Tuple[str, List[str]]:
    """스크립트를 문장 단위로 인덱싱하여 반환"""
    sentences = [s.strip() for s in raw_text.split('.') if s.strip()]
    indexed = "\n".join(f"[{i}] {s}" for i, s in enumerate(sentences))
    return indexed, sentences


def extract_evidence(result: dict, sentences: List[str], window: int = 2) -> dict:
    """LLM이 반환한 인덱스로 실제 원문을 추출"""
    ev = result["evaluation_results"]

    indices = ev["예시 적절성"].get("example_indices", [])
    spans = []
    for idx in indices:
        start = max(0, idx - window)
        end = min(len(sentences) - 1, idx + window)
        spans.append(" ".join(sentences[start:end + 1]))
    ev["예시 적절성"]["원문"] = spans

    t = ev["실습 연계"].get("theory_span", [0, 0])
    p = ev["실습 연계"].get("practice_span", [0, 0])
    ev["실습 연계"]["원문"] = {
        "이론구간": " ".join(sentences[t[0]:t[1] + 1]),
        "실습구간": " ".join(sentences[p[0]:p[1] + 1])
    }

    events = ev["오류 대응"].get("error_events", [])
    extracted = []
    for event in events:
        e_idx = event.get("error_idx", 0)
        r_indices = event.get("response_indices", [])
        extracted.append({
            "오류": sentences[e_idx] if e_idx < len(sentences) else "",
            "대응": " ".join(sentences[i] for i in r_indices if i < len(sentences))
        })
    ev["오류 대응"]["원문"] = extracted

    return result


_FUZZY_VALID     = 85
_FUZZY_WARNING   = 70

_CATEGORY_KEYS = ["예시 적절성", "실습 연계", "오류 대응"]

_SCORE_FEEDBACK: dict = {
    "예시 적절성": {
        0: {"잘한_점": "해당 없음 (평가 불가)",
            "개선_필요": "스크립트에 예시 적절성을 판단할 수 있는 내용이 없습니다.",
            "추천_개선": "강의 내용에 실무 예시를 최소 1개 이상 포함하여 재촬영을 권장합니다."},
        1: {"잘한_점": "강의 구성 자체는 존재합니다.",
            "개선_필요": "실무와 동떨어진 인위적 예시 또는 예시 자체가 부재합니다.",
            "추천_개선": "실제 현업에서 접할 수 있는 데이터/시나리오로 예시를 전면 교체하세요."},
        2: {"잘한_점": "예시를 제시하려는 시도가 있습니다.",
            "개선_필요": "예시가 지나치게 단순하거나 추상적이어서 실무 적용 가능성이 낮습니다.",
            "추천_개선": "예시에 구체적인 수치, 도메인 맥락, 실제 발생 가능한 조건을 추가하세요."},
        3: {"잘한_점": "이론과 예시의 주제가 일치하며 기본적인 사례 제시가 이루어집니다.",
            "개선_필요": "Toy Project 수준의 단순화된 예시로, 현업 복잡성이 반영되지 않았습니다.",
            "추천_개선": "실제 업무 환경의 제약 조건(데이터 이상값, 예외 케이스 등)을 예시에 포함하세요."},
        4: {"잘한_점": "실무 맥락이 충분히 반영된 예시로 학습자가 현업 연결을 쉽게 인식합니다.",
            "개선_필요": "도메인 특수성이나 복잡성이 일부 생략되어 완전한 실무 시나리오에는 미치지 못합니다.",
            "추천_개선": "도메인 고유의 제약 조건이나 실제 복잡도를 한 단계 더 반영하면 5점 수준에 도달합니다."},
        5: {"잘한_점": "현업 복잡성과 도메인 특성을 완벽히 반영한 실무형 예시입니다. 학습자의 사전 경험을 자연스럽게 활성화합니다.",
            "개선_필요": "현재 수준을 유지하세요.",
            "추천_개선": "다음 강의에서도 동일한 수준의 실무 시나리오 기반 예시 설계를 적용하세요."},
    },
    "실습 연계": {
        0: {"잘한_점": "해당 없음 (평가 불가)",
            "개선_필요": "이론/실습 구분이 불가능한 구성입니다.",
            "추천_개선": "이론 설명 구간과 실습 수행 구간을 명확히 분리하여 강의를 재설계하세요."},
        1: {"잘한_점": "강의 내용 자체는 전달됩니다.",
            "개선_필요": "이론과 실습이 완전히 분절되어 있으며 브릿지(Bridge) 설명이 전혀 없습니다.",
            "추천_개선": "이론 설명 직후 '방금 배운 X 개념을 Y 실습에서 적용해 보겠습니다'와 같은 전환 문장을 반드시 삽입하세요."},
        2: {"잘한_점": "이론과 실습의 주제가 느슨하게 연결되어 있습니다.",
            "개선_필요": "전환 시점에 안내 없이 실습이 시작되어 학습자가 맥락을 스스로 파악해야 합니다.",
            "추천_개선": "실습 시작 전 '왜 이 실습을 하는지(Why)'를 한 문장으로 명시하는 전환 안내를 추가하세요."},
        3: {"잘한_점": "이론과 실습의 주제가 일치합니다.",
            "개선_필요": "이론에서 강조한 핵심 개념이 실습에서 어떻게 적용되는지 연결 설명(Why & How)이 부족합니다.",
            "추천_개선": "이론 → 실습 전환 시 핵심 개념이 실습의 어느 단계에서 사용되는지 명시적으로 연결하세요."},
        4: {"잘한_점": "이론과 실습의 연결이 대체로 자연스럽습니다.",
            "개선_필요": "이론의 일부 개념이 실습에 반영되지 않거나 전환 설명이 간략히 생략된 부분이 있습니다.",
            "추천_개선": "이론에서 다룬 모든 핵심 개념이 실습 단계에서 1:1로 대응되도록 실습 과제를 보완하세요."},
        5: {"잘한_점": "이론과 실습이 완벽히 연결되며 학습자의 인지 부하를 최소화하는 매끄러운 브릿지가 설계되었습니다.",
            "개선_필요": "현재 수준을 유지하세요.",
            "추천_개선": "이 강의의 이론-실습 연계 구조를 템플릿으로 삼아 다른 강의 설계에도 적용하세요."},
    },
    "오류 대응": {
        0: {"잘한_점": "해당 없음 (평가 불가)",
            "개선_필요": "실습 구간이 없어 오류 대응 여부를 판단할 수 없습니다.",
            "추천_개선": "실습 구간을 강의에 포함하고, 예상 오류 시나리오에 대한 대응 발화를 설계하세요."},
        1: {"잘한_점": "강의 흐름 자체는 유지됩니다.",
            "개선_필요": "오류/예외 상황에 대한 안내가 전혀 없어 학습자가 실습 중단 위험에 노출됩니다.",
            "추천_개선": "발생 빈도가 높은 오류 2~3가지를 선정하고 각각에 대한 원인 설명과 해결 절차를 스크립트에 추가하세요."},
        2: {"잘한_점": "오류 발생 가능성을 인지하고 있습니다.",
            "개선_필요": "'무시하세요', '넘어가세요' 수준의 소극적 대응으로 학습자 이해를 돕지 못합니다.",
            "추천_개선": "단순 회피 안내 대신 '이 오류는 X 때문에 발생하며, Y를 확인하면 해결됩니다'와 같은 원인 중심 설명으로 교체하세요."},
        3: {"잘한_점": "오류 해결 방법을 명확히 제시합니다.",
            "개선_필요": "왜 그 오류가 발생했는지 시스템적 원인이나 배경 설명이 생략되어 있습니다.",
            "추천_개선": "해결 코드/방법 제시 전에 '이 오류가 발생하는 이유'를 1~2문장으로 먼저 설명하는 구조로 변경하세요."},
        4: {"잘한_점": "오류 원인 설명이 포함되어 있습니다.",
            "개선_필요": "강사가 직접 원인과 해결책을 제시하는 방식으로, 학습자 스스로 추론하도록 유도하는 스캐폴딩이 부족합니다.",
            "추천_개선": "'이 오류를 보셨을 때 어디를 먼저 확인하시겠어요?'처럼 학습자의 사고를 먼저 유도한 뒤 답을 제시하는 구조를 도입하세요."},
        5: {"잘한_점": "선제적 오류 경고 또는 디버깅 경로 안내가 설계되어 학습자의 메타인지를 자극합니다.",
            "개선_필요": "현재 수준을 유지하세요.",
            "추천_개선": "이 오류 대응 구조를 커리큘럼 전반의 표준 패턴으로 확산 적용하세요."},
    },
}


def _split_sentences(script: str) -> List[str]:
    """스크립트를 문장 단위로 분리 (줄바꿈 + 구두점 기준)"""
    sentences = []
    for line in script.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r'(?<=[.?!])\s+', line)
        sentences.extend(p.strip() for p in parts if p.strip())
    return sentences


def _fuzzy_search(query: str, sentences: List[str]) -> Tuple[float, int, str]:
    """sentences 중 query와 가장 유사한 문장의 (점수, 인덱스, 문장)을 반환"""
    best_score, best_idx, best_sent = 0.0, 0, ""
    for i, sent in enumerate(sentences):
        score = _fuzz.partial_ratio(query, sent)
        if score > best_score:
            best_score, best_idx, best_sent = score, i, sent
    return best_score, best_idx, best_sent


def _build_context(sentences: List[str], idx: int, window: int = 2) -> str:
    """idx 기준 앞뒤 window 문장을 합쳐 컨텍스트 반환"""
    start = max(0, idx - window)
    end   = min(len(sentences) - 1, idx + window)
    return " ".join(sentences[start:end + 1])


def verify_extracted_text(extracted: str, script: str, sentences: List[str], window: int = 2) -> dict:
    """
    원문 검증:
      1) 완전 일치: 스크립트에 해당 문자열이 그대로 존재하는지 확인
      2) 유사도 검사: rapidfuzz로 가장 유사한 구간 탐색 (임계값 완화)
    """
    if not extracted or not extracted.strip():
        return {"유효": False, "판정": "원문이 비어 있습니다."}

    extracted = extracted.strip()

    script_normalized    = re.sub(r'\s+', ' ', script)
    extracted_normalized = re.sub(r'\s+', ' ', extracted)
    if extracted_normalized in script_normalized:
        return {"유효": True, "판정": "완전 일치 확인"}

    if not _FUZZY_AVAILABLE:
        return {"유효": True, "판정": "rapidfuzz 미설치 — 검증 생략, 원문 유지"}

    words     = script_normalized.split()
    ext_words = extracted_normalized.split()
    chunk_size = max(len(ext_words), 10)

    best_score = 0.0
    for i in range(0, max(1, len(words) - chunk_size + 1), max(1, chunk_size // 2)):
        chunk = ' '.join(words[i:i + chunk_size])
        score = _fuzz.partial_ratio(extracted_normalized, chunk)
        if score > best_score:
            best_score = score

    valid = best_score >= 60
    return {
        "유효": valid,
        "유사도": round(best_score, 1),
        "판정": f"유사도 {best_score:.1f}점 — {'유효' if valid else '미달(원문 제거)'}"
    }


def _generate_feedback(category: str, score: int) -> dict:
    """카테고리 + 점수 → 잘한 점 / 개선 필요 / 추천 개선 반환"""
    tmpl = _SCORE_FEEDBACK.get(category, {}).get(score)
    if tmpl is None:
        return {"잘한_점": "점수 범위 오류", "개선_필요": "점수 범위 오류", "추천_개선": "점수 범위 오류"}
    return dict(tmpl)


def postprocess_evaluation(llm_result: dict, raw_script: str, window: int = 2) -> dict:
    """LLM 평가 결과에 원문 검증 + 카테고리 피드백을 추가합니다."""
    sentences = _split_sentences(raw_script)
    evals = llm_result.get("evaluation_results", {})

    for category in _CATEGORY_KEYS:
        if category not in evals:
            continue

        item  = evals[category]
        score = _safe_int(item.get("점수", 0))
        원문   = item.get("원문", "") or ""

        verification = verify_extracted_text(원문, raw_script, sentences, window)
        if not verification["유효"]:
            item["원문"] = ""

        item["피드백"] = _generate_feedback(category, score)

    return llm_result


def extract_speaker_ids_from_transcript(transcript: str) -> List[str]:
    """대화형 녹취록에서 발화자 식별자 목록을 추출합니다."""
    speaker_pattern = re.compile(r"^<\d{2}:\d{2}:\d{2}>\s*([^:]+):", re.MULTILINE)
    speakers = []
    for match in speaker_pattern.finditer(transcript):
        speaker = match.group(1).strip()
        if speaker and speaker not in speakers:
            speakers.append(speaker)
    return speakers


def normalize_transcript(transcript: str) -> str:
    """타임스탬프와 발화자를 정리하여 본문 텍스트를 간결하게 만듭니다."""
    normalized = re.sub(r"^<\d{2}:\d{2}:\d{2}>\s*", "", transcript, flags=re.MULTILINE)
    return normalized.strip()


LECTURE_FILE = Path(r"강의 스크립트\2026-02-01_kdt-backendj-22th.txt")


def load_lecture_script(file_path: str) -> str:
    """강의 스크립트 파일을 읽기"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")
    except Exception as e:
        raise Exception(f"파일 읽기 중 오류 발생: {e}")


def _safe_int(x):
    try:
        if x is None:
            return 0
        if isinstance(x, (int, float)):
            return int(x)
        s = str(x).strip()
        if s == "":
            return 0
        return int(float(s))
    except Exception:
        return 0


def create_nested_schema(obj: dict, file_name: Optional[str] = None) -> dict:
    """모델 출력(기존 포맷)을 사용자가 원하는 중첩 구조로 변환합니다."""
    out = {}
    fname = (file_name or obj.get("강의자") or obj.get("file_name") or "result")
    evals = (
        obj.get("evaluation_results")
        or obj.get("evaluationResults")
        or obj.get("평가 결과")
        or obj.get("evaluation")
        or {}
    )
    if not isinstance(evals, dict):
        return obj

    out[fname] = {}
    for idx, (k, v) in enumerate(evals.items(), start=1):
        if not isinstance(v, dict):
            continue

        score    = v.get("점수") if v.get("점수") is not None else v.get("score") if v.get("score") is not None else v.get("Score")
        original = v.get("원문") if v.get("원문") is not None else v.get("original") if v.get("original") is not None else v.get("evidence")
        reason   = v.get("판정근거") if v.get("판정근거") is not None else v.get("reason") if v.get("reason") is not None else v.get("근거")

        entry = {
            "점수":    _safe_int(score),
            "카테고리": k,
            "원문":    original or "",
            "판정근거": reason or "",
        }

        if v.get("피드백"):
            entry["피드백"] = v["피드백"]

        out[fname][str(idx)] = entry

    for meta_key in ("강의자", "overall_summary", "actionable_recommendations"):
        if obj.get(meta_key):
            out[meta_key] = obj[meta_key]

    return out


def analyze_lecture(lecture_text: str, custom_prompt: Optional[str] = None, api_key: Optional[str] = None, file_name: Optional[str] = None, **kwargs) -> str:
    """
    Gemini API를 사용하여 강의 스크립트를 분석합니다.

    Args:
        lecture_text: 강의 스크립트 텍스트
        custom_prompt: 커스텀 프롬프트 (None일 경우 기본 프롬프트 사용)
        api_key: API 키 (None이면 파일 상단 설정 또는 환경 변수 사용)
        file_name: 출력 JSON의 최상위 키로 사용할 파일명

    Returns:
        분석 결과 JSON 문자열
    """
    if custom_prompt is None:
        custom_prompt = DEFAULT_PROMPT

    system_prompt = "당신은 교육 콘텐츠 전문가입니다. 강의 스크립트를 분석하고 핵심 내용을 정리해줍니다."

    speaker_ids     = extract_speaker_ids_from_transcript(lecture_text)
    normalized_text = normalize_transcript(lecture_text)
    speaker_note    = ""
    if speaker_ids:
        speaker_note = (
            "추가 정보: 이 녹취록에는 다음과 같은 발화자 식별자가 포함되어 있습니다. "
            f"{', '.join(speaker_ids)}.\n"
            "주된 강의자 정보를 가능한 한 '강의자' 항목에 반영하고, "
            "발화자 이름을 그대로 사용하여 결과에 포함하세요.\n"
        )

    full_prompt = (
        f"{system_prompt}\n\n{custom_prompt}\n\n"
        f"{speaker_note}\n"
        "=== 강의 스크립트 ===\n"
        f"{normalized_text}"
    )
    gemini_client, gemini_model_name = get_gemini_model(api_key=api_key)
    response = gemini_client.models.generate_content(
        model=gemini_model_name,
        contents=full_prompt,
        config=genai_types.GenerateContentConfig(
            max_output_tokens=2048,
            temperature=0.0,
        )
    )
    response_text = response.text if hasattr(response, "text") else str(response)
    print(f"  [모델: {GEMINI_MODEL}]")

    def extract_first_json(s: str) -> Optional[str]:
        start = s.find("{")
        if start == -1:
            return None
        in_str = False
        esc    = False
        depth  = 0
        for i in range(start, len(s)):
            ch = s[i]
            if ch == '"' and not esc:
                in_str = not in_str
            if ch == '\\' and not esc:
                esc = True
                continue
            else:
                esc = False
            if not in_str:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        return s[start:i+1]
        return None

    def _process(obj: dict) -> str:
        obj = postprocess_evaluation(obj, normalized_text)
        try:
            nested = create_nested_schema(obj, file_name=file_name)
            return json.dumps(nested, ensure_ascii=False)
        except Exception:
            return json.dumps(obj, ensure_ascii=False)

    try:
        parsed = json.loads(response_text)
        return _process(parsed)
    except Exception:
        pass

    extracted = extract_first_json(response_text)
    if extracted:
        try:
            return _process(json.loads(extracted))
        except Exception:
            return response_text

    return response_text


def save_analysis_result(result: str, output_file: str = None) -> str:
    """분석 결과를 파일로 저장"""
    if output_file is None:
        output_file = OUTPUT_DIR / "lecture_analysis_result.json"

    output_path = Path(output_file)
    if not output_path.is_absolute():
        output_path = OUTPUT_DIR / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    json_text = result
    try:
        parsed_json = json.loads(result)
        json_text = json.dumps(parsed_json, ensure_ascii=False, indent=2)
    except Exception:
        pass

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(json_text)
        print(f"분석 결과가 저장되었습니다: {output_path}")
        return str(output_path)
    except Exception as e:
        raise Exception(f"파일 저장 중 오류 발생: {e}")


def main(custom_prompt: Optional[str] = None, lecture_file: Optional[Path] = None):
    """Gemini로 분석 후 결과를 json 폴더에 저장합니다."""
    try:
        if lecture_file is None:
            lecture_file = LECTURE_FILE
        if lecture_file is None:
            raise ValueError("강의 스크립트 파일이 지정되지 않았습니다.")

        print(f"강의 스크립트 로드 중: {lecture_file}")
        lecture_text = load_lecture_script(str(lecture_file))
        print(f"파일 크기: {len(lecture_text)} 글자")

        file_stem = Path(str(lecture_file)).stem

        print(f"\nGemini API ({GEMINI_MODEL}) 분석 중...")
        gemini_result = analyze_lecture(
            lecture_text,
            custom_prompt=custom_prompt,
            file_name=file_stem,
        )
        gemini_output = OUTPUT_DIR / f"{file_stem}_gemini.json"
        save_analysis_result(gemini_result, output_file=gemini_output)

        print("\n=== 분석 완료 ===")
        print(f"  결과: {gemini_output}")
        return str(gemini_output)

    except Exception as e:
        print(f"오류 발생: {e}")
        raise


# ── test.py 핵심 함수 이식 ───────────────────────────────────
def _safe_int(x) -> int:
    try:
        if x is None:
            return 0
        if isinstance(x, (int, float)):
            return int(x)
        s = str(x).strip()
        return int(float(s)) if s else 0
    except Exception:
        return 0

def extract_speaker_ids(transcript: str) -> list[str]:
    pattern = re.compile(r"^<\d{2}:\d{2}:\d{2}>\s*([^:]+):", re.MULTILINE)
    seen, result = set(), []
    for m in pattern.finditer(transcript):
        sp = m.group(1).strip()
        if sp and sp not in seen:
            seen.add(sp)
            result.append(sp)
    return result

def normalize_transcript(transcript: str) -> str:
    return re.sub(r"^<\d{2}:\d{2}:\d{2}>\s*", "", transcript, flags=re.MULTILINE).strip()

def build_timestamp_index(raw_transcript: str) -> list[tuple[str, str]]:
    """
    원본 스크립트에서 (timestamp, line_text) 쌍의 인덱스를 만듭니다.
    타임스탬프가 없는 줄은 직전 타임스탬프를 이어받습니다.

    지원 형식:
        <HH:MM:SS> 발화자ID: 텍스트   (예: <09:10:22> 23033da8: 안녕하세요.)
        <HH:MM:SS> 텍스트             (발화자 없는 경우)
    """
    # 발화자ID가 있는 경우와 없는 경우 모두 처리
    ts_pattern = re.compile(r"^<(\d{2}:\d{2}:\d{2})>\s*(?:[^:\s]+:\s*)?(.*)")
    index: list[tuple[str, str]] = []
    last_ts = ""
    for line in raw_transcript.splitlines():
        m = ts_pattern.match(line)
        if m:
            last_ts = m.group(1)
            text    = m.group(2).strip()
        else:
            text = line.strip()
        if text:
            index.append((last_ts, text))
    return index

def find_timestamp_for_evidence(evidence_text: str, ts_index: list[tuple[str, str]]) -> str:
    """
    evidence 원문과 가장 유사한 줄을 ts_index에서 찾아 타임스탬프를 반환합니다.
    완전 일치 우선, 없으면 rapidfuzz 유사도로 탐색합니다.
    """
    ev_norm = re.sub(r"\s+", " ", evidence_text.strip())

    # 1단계: 완전 포함 일치
    for ts, line in ts_index:
        line_norm = re.sub(r"\s+", " ", line)
        if ev_norm in line_norm or line_norm in ev_norm:
            return ts

    # 2단계: rapidfuzz 유사도
    if _FUZZY_AVAILABLE:
        best_score, best_ts = 0.0, ""
        for ts, line in ts_index:
            line_norm = re.sub(r"\s+", " ", line)
            score = _fuzz.partial_ratio(ev_norm, line_norm)
            if score > best_score:
                best_score, best_ts = score, ts
        if best_score >= 60:
            return best_ts

    return ""

def verify_evidence(text: str, script: str) -> bool:
    if not text or not text.strip():
        return False
    t = re.sub(r'\s+', ' ', text.strip())
    s = re.sub(r'\s+', ' ', script)
    if t in s:
        return True
    if not _FUZZY_AVAILABLE:
        return True
    words      = s.split()
    ext_words  = t.split()
    chunk_size = max(len(ext_words), 10)
    best = 0.0
    for i in range(0, max(1, len(words) - chunk_size + 1), max(1, chunk_size // 2)):
        chunk = ' '.join(words[i:i + chunk_size])
        score = _fuzz.partial_ratio(t, chunk)
        if score > best:
            best = score
    return best >= 60

def clean_json_text(text: str) -> str:
    """LLM 응답에서 마크다운 코드 블록 등을 제거하고 순수 JSON만 추출합니다."""
    # ```json ... ``` 또는 ``` ... ``` 제거
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.replace("```", "").strip()
    return text

def extract_first_json(s: str) -> str | None:
    """문자열에서 첫 번째 완전한 JSON 객체를 추출합니다."""
    start = s.find("{")
    if start == -1:
        return None
    in_str, esc, depth = False, False, 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == '"' and not esc:
            in_str = not in_str
        esc = (ch == '\\' and not esc)
        if not in_str:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return s[start:i + 1]
    return None

def build_output(meta: dict, llm_items: dict, normalized_script: str, ts_index: list) -> dict:
    items_out = {}

    for key in ("4.1", "4.2", "4.3"):
        raw   = llm_items.get(key, {})
        score = _safe_int(raw.get("score", 0))

        # evidence 검증
        raw_evidence = raw.get("evidence", [])
        if isinstance(raw_evidence, str):
            raw_evidence = [raw_evidence] if raw_evidence.strip() else []

        validated_evidence = []
        for ev in raw_evidence:
            if not isinstance(ev, str) or not ev.strip():
                continue
            if not verify_evidence(ev, normalized_script):
                continue
            ts = find_timestamp_for_evidence(ev, ts_index)
            validated_evidence.append({
                "source":    ev.strip(),
                "timestamp": ts,
            })

        # LLM이 생성한 피드백을 그대로 사용
        raw_feedback = raw.get("feedback", {}) or {}
        feedback = {
            "weakness":   (raw_feedback.get("weakness")   or "").strip(),
            "suggestion": (raw_feedback.get("suggestion") or "").strip(),
            "example":    (raw_feedback.get("example")    or "").strip(),
        }

        # 5점이거나 evidence 없으면 example → "해당 사항 없음" 강제
        if score == 5 or not validated_evidence:
            feedback["example"] = "해당 사항 없음"

        # weakness/suggestion이 비어 있을 경우 기본값 보호
        if not feedback["weakness"]:
            feedback["weakness"] = "해당 사항 없음" if score == 5 else ""
        if not feedback["suggestion"]:
            feedback["suggestion"] = "현재 수준을 유지하세요." if score == 5 else ""

        items_out[key] = {
            "score":    score,
            "reason":   (raw.get("reason") or "").strip(),
            "evidence": validated_evidence,
            "feedback": feedback,
        }

    return {
        "file_name":  meta["file_name"],
        "date":       meta["date"],
        "instructor": meta["instructor"],
        "course_id":  meta["course_id"],
        "items":      items_out,
    }

def call_gemini(lecture_text: str) -> tuple[dict, str, list]:
    """강의 스크립트를 분석하고 (items dict, normalized_script, ts_index)를 반환합니다."""
    _api_key = (os.environ.get("GCP_API_KEY") or
               os.environ.get("GEMINI_API_KEY") or
               os.environ.get("GOOGLE_API_KEY") or
               GEMINI_API_KEY or "")
    if not _api_key or _api_key == "your-api-key":
        raise ValueError("Gemini API 키가 설정되지 않았습니다.")

    normalized      = normalize_transcript(lecture_text)
    ts_index        = build_timestamp_index(lecture_text)
    speaker_ids     = extract_speaker_ids(lecture_text)
    speaker_note    = ""
    if speaker_ids:
        speaker_note = f"발화자 식별자: {', '.join(speaker_ids)}\n주된 강의자 정보를 판단에 활용하세요.\n\n"

    full_prompt = (
        DEFAULT_PROMPT + "\n\n"
        + speaker_note
        + "=== 강의 스크립트 ===\n"
        + normalized
    )

    # google-genai 신패키지 클라이언트
    client   = genai.Client(api_key=_api_key)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=full_prompt,
        config=genai_types.GenerateContentConfig(
            max_output_tokens=8192,
            temperature=0.0,
        ),
    )

    # 응답 텍스트 안전하게 추출 (candidates → parts 순서로 접근)
    raw_text = ""
    try:
        for cand in response.candidates:
            for part in cand.content.parts:
                if hasattr(part, "text"):
                    raw_text += part.text
    except Exception:
        pass
    if not raw_text:
        raw_text = response.text if hasattr(response, "text") else str(response)

    # 마크다운 코드 블록 제거 후 JSON 파싱 시도
    cleaned = clean_json_text(raw_text)

    for candidate in [cleaned, extract_first_json(cleaned), extract_first_json(raw_text)]:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            items  = parsed.get("items", parsed)
            return items, normalized, ts_index
        except json.JSONDecodeError:
            continue

    # 파싱 실패 시 원본 출력 후 예외
    print("\n[DEBUG] Gemini 원본 응답 (처음 1000자):")
    print(raw_text[:1000])
    raise ValueError("Gemini 응답을 JSON으로 파싱할 수 없습니다. 위 DEBUG 출력을 확인하세요.")


if __name__ == "__main__":
    import sys as _sys, io as _io, json as _json, re as _re2
    _sys.stdout = _io.TextIOWrapper(_sys.stdout.buffer, encoding='utf-8', errors='replace')
    _sys.stderr = _io.TextIOWrapper(_sys.stderr.buffer, encoding='utf-8', errors='replace')

    if len(_sys.argv) == 2 and _sys.argv[1].endswith(".txt") and not any(
        a.startswith("--") for a in _sys.argv[1:]
    ):
        _txt_path = _sys.argv[1]
        try:
            from pathlib import Path as _Path
            _stem  = _Path(_txt_path).stem
            _fname = _Path(_txt_path).name
            _m     = _re2.match(r'^(\d{4}-\d{2}-\d{2})_(.+)$', _stem)
            _meta  = {
                'file_name':  _fname,
                'date':       _m.group(1) if _m else '',
                'course_id':  _m.group(2) if _m else _stem,
                'instructor': '',
            }
            with open(_txt_path, "r", encoding="utf-8") as _f:
                _text = _f.read()
            _llm_items, _norm, _ts_idx = call_gemini(_text)
            _output = build_output(_meta, _llm_items, _norm, _ts_idx)
            print(_json.dumps(_output, ensure_ascii=False))
        except Exception as _e:
            print(_json.dumps({"error": str(_e)}, ensure_ascii=False))
        _sys.exit(0)
    main()