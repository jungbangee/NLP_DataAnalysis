"""
v7_gemini.py - 카테고리 2 채점 (Gemini 전환판)

[v7 특징 — v6 대비]
- 모델 제공자 전환: Claude(Anthropic) → Gemini(Google, GCP 크레딧 사용)
- 호출부만 교체, 나머지 로직(구조화 evidence / 원문 검증 / 퍼지매칭 / 강사 피드백)은 v6 그대로
- 인증: .env의 GCP_API_KEY (AIza... Gemini 키)
- 구조화 출력: google-genai response_schema(Pydantic) → response.parsed

[주의] Gemini는 Claude와 다른 모델이라 같은 강의도 점수가 다를 수 있음.
        v6(Claude) 결과와 직접 비교 불가. 비용 한도 회피용 임시 채점기로 사용.
"""
import json
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

_CATE2_DIR = Path(__file__).parent
sys.path.insert(0, str(_CATE2_DIR))
sys.path.insert(0, str(_CATE2_DIR.parent))
from utils import parse_file, get_utterances, extract_opening, extract_closing, extract_sampled, extract_full
from rubrics import V2_RUBRICS, SYSTEM_PROMPT, CATEGORY2_ITEMS, calc_category_score, score_to_100

load_dotenv()

TARGET_FILE = "2026-02-02_kdt-backendj-21th.txt"
MODEL = "gemini-3.1-pro-preview"  # 3.1 Pro로 교체 (5사이클 가드 동일 적용)
CYCLE = "g31full"  # 3.1pro + 2.3·2.4 전체구간 + 퓨샷 라벨 수정
RESULTS_DIR = Path(__file__).parent.parent / "results" / "v7"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

_HARDCODED_KEY = "AIzaSyB-ZoAe_gLepBQMoqBxHipAu6Qqyg-bP6U"
_client = None

def get_client():
    global _client
    if _client is None:
        api_key = (os.environ.get("GCP_API_KEY") or
                   os.environ.get("GEMINI_API_KEY") or
                   os.environ.get("GOOGLE_API_KEY") or
                   _HARDCODED_KEY)
        _client = genai.Client(api_key=api_key)
    return _client

class _ClientProxy:
    def __getattr__(self, name):
        return getattr(get_client(), name)

client = _ClientProxy()

# ── 채점 보정 예시 ───────────────────────────────────────────────────
# #2 수정: "같은 강의 사례"라는 거짓 라벨 제거 → 일반 보정 예시로 명시.
#   (--file로 다른 강의를 채점해도 라벨이 사실에 부합하도록)
FEWSHOT_EXAMPLES = {
    "2.1": """
[채점 보정 예시 - 참고용 자바 강의 사례 (현재 채점 대상과 무관한 일반 예시)]

예시 A (3점):
발화: "자 저희 오늘 수업 진행하도록 하겠습니다. 저희가 이제 오늘 1차 잡바 마지막 날입니다. 그래서 지난 시간에 제너릭 타입을 이용을 해서 커스텀 컬렉션을 활용한 크루드 방법을 학습 이해를 하고 그다음에 데이터 흐름 읽기 쓰기를 구현하는 날이에요. NIO 패키지가 있고 그 다음에 NIO2라는 패키지를 가지고 있는데, 이걸 세 가지 섹션으로 나눠서 진행을 하고 있습니다."
채점: 3점 / 오늘 다룰 주제(IO, NIO, NIO2)는 언급되었으나 각 주제별 학습 순서와 목표가 불명확.

예시 B (5점, 가상 이상적 사례):
발화: "오늘은 자바 IO, NIO, NIO2 세 섹션을 순서대로 진행합니다. 첫째로 IO에서는 기본 파일 읽기/쓰기를 배우고, 둘째로 NIO에서는 버퍼와 채널 개념을, 셋째로 NIO2에서는 Path API를 실습합니다. 오늘 수업 후 여러분은 세 가지 방식의 차이점을 설명할 수 있어야 합니다."
채점: 5점 / 순서(IO→NIO→NIO2), 각 섹션의 내용, 기대 성과까지 명시적으로 안내됨.
""",

    "2.2": """
[채점 보정 예시 - 참고용 자바 강의 사례 (현재 채점 대상과 무관한 일반 예시)]

예시 A (3점):
발화: "지난 시간에 제너릭 타입을 이용을 해서 커스텀 컬렉션을 활용한 크루드 방법을 학습 이해를 하고"
채점: 3점 / 어제 배운 내용을 언급했지만 오늘 IO/NIO 학습과의 명시적 연결고리가 없음.

예시 B (5점, 가상 이상적 사례):
발화: "어제 제너릭으로 커스텀 컬렉션을 만들었죠. 컬렉션에 데이터를 넣고 뺐는데, 오늘은 그 데이터를 파일에 저장하고 불러오는 방법을 배웁니다."
채점: 5점 / 어제 내용 복습 + 오늘 내용과 "파일에 저장/불러오기"로 명시적 연결.
""",

    "2.5": """
[채점 보정 예시 - 참고용 자바 강의 사례 (현재 채점 대상과 무관한 일반 예시)]

예시 A (3점):
발화: "오늘은 I이O하고 N아IO2를 이제 기점으로 봤고 내일 아침에 와서 DB 들어가기 전에 길을 한번 가서 제가 한번 짚고 갈 거거든요."
채점: 3점 / 오늘 다룬 내용을 간략히 언급하고 내일 예고는 있으나, 핵심 개념의 명시적 요약 없이 넘어감.

예시 B (5점, 가상 이상적 사례):
발화: "오늘 IO, NIO, NIO2 세 패키지를 봤습니다. IO는 기본 스트림, NIO는 버퍼+채널, NIO2는 Path API가 핵심입니다. 이 세 가지 차이점을 꼭 기억하세요. 내일은 이걸 활용해서 DB 연동을 진행합니다."
채점: 5점 / 핵심 내용 항목별 요약 + 핵심 강조 + 내일 예고까지 완비.
""",

    "2.3": """
[퓨샷 예시 - 점수 경계 보정]

예시 A (2점, 흔한 실제 패턴):
상황: 강사가 개념을 설명한 뒤, 곧바로 IDE의 API 문서(도움말)를 띄워 메소드 목록을 훑어보거나, 기존 코드 파일을 '컨트롤 C 컨트롤 V'로 복사해 일부만 수정하며 진행함. 강사가 빈 화면에서 처음부터 끝까지 작성하는 '완성된 worked example' 시연은 대부분 생략됨.
채점: 2점 / API 문서 열람과 코드 복붙은 worked example이 아님. 개념→예시→실습의 '예시' 단계가 사실상 비어 있어 순서가 불규칙하게 혼재함.

예시 B (5점, 가상 이상적 사례):
상황: 개념 정의 → 강사가 빈 파일에서 전체 코드를 직접 한 줄씩 작성·실행하며 시연 → 학생에게 동일 패턴의 과제 부여. 이 3단계가 강의 전체에 걸쳐 일관되게 반복됨.
채점: 5점 / 개념→예시(완성 시연)→실습이 일관 유지됨.
""",

    "2.4": """
[퓨샷 예시 - 점수 경계 보정]

예시 A (2점, 흔한 실제 패턴):
발화: "이 클래스를 가장 많이 쓰니까 중점적으로 하시면 돼요." / "여기서 많이 쓰는 건 이거예요."
채점: 2점 / '중점적으로', '많이 쓰는'은 약한 방향 제시일 뿐, '이게 핵심입니다 / 꼭 기억하세요' 같은 명시적 신호화가 아님. 무엇이 핵심인지 학습자가 스스로 판단해야 함.

예시 B (5점, 가상 이상적 사례):
발화: "자, 이게 오늘 가장 중요한 핵심입니다. 꼭 기억하세요. static 필드는 직렬화 대상이 아닙니다. 다시 한 번, static은 직렬화에서 제외됩니다."
채점: 5점 / '핵심입니다/꼭 기억하세요' 명시적 신호화 + 중요 내용 반복 강조.
""",
}

DEFAULT_FEWSHOT = "[참고] 퓨샷 예시 없음 - 채점 기준과 구간 텍스트만으로 판단하세요."

EVIDENCE_INSTRUCTION = """
[evidence 작성 규칙 — 매우 중요]
- evidence는 판정 근거가 된 원문 인용문들의 '배열'입니다.
- 각 quote는 강의 스크립트 원문을 **글자 하나도 바꾸지 말고 그대로** 복사하세요.
  (요약·교정·단어 추가·맞춤법 수정 금지. STT 오타도 그대로 둘 것.)
- ★가장 중요★: 하나의 quote는 **끊기지 않은 단일 발화(한 줄)** 에서만 가져오세요.
  - 서로 떨어져 있는 두 발화를 이어붙여 하나의 quote로 만들지 마세요.
  - 원문에서 중간 단어를 건너뛰고 앞뒤만 합치지 마세요.
  - 줄바꿈(\\n)을 quote 안에 넣지 마세요. quote는 원문에 연속으로 존재하는 한 토막이어야 합니다.
  - 근거가 여러 발화에 흩어져 있으면, 각 발화를 '별도의' evidence 항목으로 나누세요.
- quote에는 타임스탬프(<...>)와 화자 ID를 포함하지 말고, 발화 텍스트만 담으세요.
- 한 발화 전체가 길면, 그 발화 안에서 연속된 일부만 잘라 써도 됩니다(연속이기만 하면 됨).
- timestamp 필드에는 해당 발화의 타임스탬프(예: "09:11:18")를 적으세요. 모르면 "".
- 해설·평가 문장은 quote에 넣지 말고 reason 필드에만 작성하세요.
- 인용은 1~3개. 점수 판단에 직접 쓰인 가장 핵심적인 발화만 고르세요.
"""

FEEDBACK_INSTRUCTION = """
[feedback 작성 규칙]
- feedback은 강사에게 줄 '구체적 개선 피드백'입니다. 막연한 칭찬·지적 금지.
- weakness: 이 항목에서 무엇이 미흡했는지 (점수가 5점이 아닌 이유). 1문장.
- suggestion: 그것을 어떻게 개선할지 구체적 행동 지침. 루브릭의 [이론 근거] 방향에 맞출 것. 1~2문장.
- example: 강사가 실제로 말하면 좋을 '개선된 멘트 예시'를 이 강의 내용(자바 IO/NIO/NIO2 등)에 맞춰 1~2문장으로 작성. 원문 인용이 아니라 새로 제안하는 문장임.
- [필수] weakness="없음"은 '오직 점수가 5점일 때만' 허용됩니다.
  4점 이하인데 weakness를 "없음"으로 두는 것은 금지입니다. 4점 이하는 반드시
  '5점이 되기 위해 무엇이 부족한지'를 weakness에 구체적으로 적고, suggestion·example도 채우세요.
- 점수가 5점이면 weakness="없음", suggestion="현 수준 유지", example=""로 작성.
"""

# ── 채점 엄격성 가드 (사이클마다 강화) ───────────────────────────────
# [c1] 반(反)관대 가드: 5점 희귀성 + 약한 강조 불인정 + 모호하면 낮은 점수
# [c2] 근거 게이트: 5점 정의의 핵심 표현이 evidence에 직접 인용으로 없으면 최대 3점
STRICTNESS_GUARD = """
[채점 엄격성 규칙 — 반드시 준수]
- 5점은 '매우 드문' 최고 등급입니다. 대부분의 실제 강의는 2~4점에 분포합니다.
- 루브릭의 각 점수 정의에 적힌 '표현/행동'이 강의에 실제로 존재해야 그 점수를 줍니다.
- 약한 표현을 상위 기준으로 과대 해석하지 마세요.
  예: '중점적으로 하세요', '많이 쓰는' 같은 약한 방향 제시를
      '이게 핵심입니다 / 꼭 기억하세요' 수준의 명시적 신호화로 인정하지 말 것.
- 근거가 모호하거나 애매하면 항상 '낮은 쪽' 점수를 선택하세요.

[근거 게이트 — 5점/4점 상한 규칙]
- 5점을 주려면, 루브릭 '5점 정의'에 적힌 핵심 표현/행동이 evidence의 quote에
  '문자 그대로' 담겨 있어야 합니다. 그런 직접 인용을 제시하지 못하면 5점을 줄 수 없습니다.
- 5점 정의의 핵심 요소가 evidence에 없으면 점수는 '최대 3점'으로 제한됩니다.
- 즉 채점 순서: ① 5점 정의의 핵심 표현을 강의에서 찾는다 → ② 찾으면 그 발화를
  evidence에 직접 인용한다 → ③ 못 찾으면 3점 이하로 채점한다.
"""


class EvidenceQuote(BaseModel):
    quote: str = Field(description="원문 그대로의 발화 (변형 금지, 타임스탬프/화자ID 제외)")
    timestamp: str = Field(description="발화 타임스탬프 예: '09:11:18'. 모르면 빈 문자열.")


class Feedback(BaseModel):
    weakness: str = Field(description="미흡한 점 (5점이 아닌 이유). 1문장. 5점이면 '없음'.")
    suggestion: str = Field(description="구체적 개선 행동 지침. 이론 근거 방향. 1~2문장.")
    example: str = Field(description="이 강의에 맞춘 개선 멘트 예시(새로 제안). 5점이면 빈 문자열.")


class ScoreResult(BaseModel):
    score: int = Field(description="0~5 정수 점수")
    reason: str = Field(description="채점 근거. 2~3문장, 200자 이내. 해설은 여기에만.")
    evidence: list[EvidenceQuote] = Field(description="판정 근거 원문 인용 1~3개")
    feedback: Feedback = Field(description="강사 개선 피드백 (weakness/suggestion/example)")


TS_RE = re.compile(r"^<\d{2}:\d{2}:\d{2}>\s*")
FUZZY_THRESHOLD = 0.7


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _containment(q_norm: str, u_norm: str) -> float:
    if not q_norm:
        return 0.0
    sm = SequenceMatcher(None, q_norm, u_norm, autojunk=False)
    matched = sum(b.size for b in sm.get_matching_blocks())
    return matched / len(q_norm)


def build_utt_index(lines: list[str]) -> list[dict]:
    index = []
    for u in get_utterances(lines):
        m = re.match(r"<(\d{2}:\d{2}:\d{2})>", u)
        ts = m.group(1) if m else ""
        text = TS_RE.sub("", u).strip()
        index.append({"ts": ts, "text": text, "norm": _normalize(text)})
    return index


def locate_quote(quote: str, source_norm: str, utt_index: list[dict]) -> dict:
    q = _normalize(quote)
    is_exact = len(q) >= 4 and q in source_norm

    best, best_score = None, 0.0
    for u in utt_index:
        score = _containment(q, u["norm"])
        if score > best_score:
            best_score, best = score, u

    if is_exact:
        match_type = "exact"
    elif best_score >= FUZZY_THRESHOLD:
        match_type = "fuzzy"
    else:
        match_type = "none"

    return {
        "quote": quote,
        "match_type": match_type,
        "similarity": round(best_score, 2),
        "timestamp": best["ts"] if best else "",
        "source": best["text"] if best else "",
    }


def score_item(item_id: str, segment: str, source_norm: str, utt_index: list[dict]) -> dict:
    """단일 항목 채점 (Gemini 호출 + v6 후처리)"""
    rubric = V2_RUBRICS[item_id]
    fewshot = FEWSHOT_EXAMPLES.get(item_id, DEFAULT_FEWSHOT)

    system = f"{SYSTEM_PROMPT}\n\n{fewshot}\n\n{EVIDENCE_INSTRUCTION}\n\n{FEEDBACK_INSTRUCTION}\n\n{STRICTNESS_GUARD}"
    user_content = f"{rubric}\n\n[분석할 강의 스크립트]\n{segment}"

    response = client.models.generate_content(
        model=MODEL,
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=ScoreResult,
            max_output_tokens=8192,
            temperature=0.0,  # [c5] 결정성 확보: 실행 간 점수 변동 최소화
            thinking_config=types.ThinkingConfig(thinking_budget=-1),  # 동적 thinking
        ),
    )

    result: ScoreResult = response.parsed
    if result is None:  # 파싱 실패 시 원문 JSON 폴백
        result = ScoreResult(**json.loads(response.text))

    um = response.usage_metadata
    in_tok = getattr(um, "prompt_token_count", 0) or 0
    out_tok = getattr(um, "candidates_token_count", 0) or 0
    think_tok = getattr(um, "thoughts_token_count", 0) or 0

    evidence = [locate_quote(ev.quote, source_norm, utt_index) for ev in result.evidence]

    return {
        "score": result.score,
        "reason": result.reason,
        "evidence": evidence,
        "feedback": {
            "weakness": result.feedback.weakness,
            "suggestion": result.feedback.suggestion,
            "example": result.feedback.example,
        },
        "tokens": {"input": in_tok, "output": out_tok + think_tok},
    }


def run_v7(fname: str = TARGET_FILE, lecture_text: str = "", file_name: str = "") -> dict:
    """
    두 가지 방식으로 호출 가능합니다.

    1. 로컬 파일:  run_v7(fname="2026-02-02_강의.txt")
    2. 웹 업로드:  run_v7(lecture_text="...", file_name="2026-02-02_강의.txt")
    """
    actual_fname = file_name or fname

    print(f"\n{'='*60}")
    print(f"  v7 채점 시작: {actual_fname}  [사이클: {CYCLE}]")
    print(f"  제공자: Google Gemini / 모델: {MODEL}")
    print(f"{'='*60}")

    if lecture_text:
        # 웹 업로드 방식: 텍스트를 줄 목록으로 변환
        lines = [l.strip() for l in lecture_text.splitlines() if l.strip()]
        print(f"  업로드 텍스트 로드: {len(lines)}줄")
    else:
        lines = parse_file(fname)
        print(f"  파일 로드: {len(lines)}줄")

    utt_index = build_utt_index(lines)
    source_norm = _normalize(" ".join(u["text"] for u in utt_index))
    print(f"  발화 인덱스: {len(utt_index)}개")

    segments = {
        "2.1": extract_opening(lines, minutes=10),
        "2.2": extract_opening(lines, minutes=15),
        "2.3": extract_full(lines),  # #1 표본 확대: 10% 샘플 → 전체 구간
        "2.4": extract_full(lines),  # #1 표본 확대: 10% 샘플 → 전체 구간
        "2.5": extract_closing(lines, minutes=30),
    }

    category_results = {}
    scores = {}
    total_input = total_output = 0
    cnt = {"exact": 0, "fuzzy": 0, "none": 0}

    for item in CATEGORY2_ITEMS:
        item_id = item["id"]
        print(f"\n  [{item_id}] {item['name']} 채점 중...", end="", flush=True)
        result = score_item(item_id, segments[item_id], source_norm, utt_index)

        category_results[item_id] = {
            "score": result["score"],
            "reason": result["reason"],
            "evidence": result["evidence"],
            "feedback": result["feedback"],
        }
        scores[item_id] = result["score"]
        total_input += result["tokens"]["input"]
        total_output += result["tokens"]["output"]

        n = len(result["evidence"])
        for e in result["evidence"]:
            cnt[e["match_type"]] += 1
        ex = sum(1 for e in result["evidence"] if e["match_type"] == "exact")
        fz = sum(1 for e in result["evidence"] if e["match_type"] == "fuzzy")
        print(f" {result['score']}/5  (인용 {n}개: exact {ex}, fuzzy {fz})")
        print(f"    미흡: {result['feedback']['weakness'][:60]}")

    category_score = calc_category_score(scores)
    final_100 = score_to_100(category_score)
    # Gemini 대략 단가 (입력/출력 $/1M, thinking은 출력에 포함)
    PRICING = {
        "gemini-3.1-pro-preview": (1.25, 10.00),  # 추정치 (정확 단가 미공개)
        "gemini-2.5-pro": (1.25, 10.00),
        "gemini-2.5-flash": (0.30, 2.50),
    }
    in_rate, out_rate = PRICING.get(MODEL, (0.30, 2.50))
    cost = total_input * in_rate / 1_000_000 + total_output * out_rate / 1_000_000

    total_q = cnt["exact"] + cnt["fuzzy"] + cnt["none"]
    highlightable = cnt["exact"] + cnt["fuzzy"]

    print(f"\n{'─'*60}")
    print(f"  카테고리 2 최종 점수: {category_score:.2f}/5.0 → {final_100:.1f}/100")
    if total_q:
        print(f"  하이라이트 가능: {highlightable}/{total_q} ({100*highlightable/total_q:.0f}%)"
              f"  [exact {cnt['exact']} / fuzzy {cnt['fuzzy']} / none {cnt['none']}]")
    print(f"  토큰: 입력 {total_input:,} / 출력+thinking {total_output:,}")
    print(f"  추정 비용: ${cost:.5f} (~= KRW{cost*1400:.1f}원)  ※GCP 크레딧 차감")
    print(f"{'─'*60}")

    output = {
        "file_name": actual_fname,
        "provider": "gemini",
        "model": MODEL,
        "cycle": CYCLE,
        "category": category_results,
        "category_score": round(category_score, 3),
        "score_100": round(final_100, 1),
    }
    # 로컬 파일 방식일 때만 저장
    if not lecture_text:
        out_path = RESULTS_DIR / f"v7_{CYCLE}_{actual_fname.replace('.txt', '.json')}"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n  결과 저장: {out_path}")
    return output


def analyze_from_upload(lecture_text: str, file_name: str) -> dict:
    """
    웹에서 업로드된 txt 파일을 카테고리 2 채점합니다.

    Args:
        lecture_text : 업로드된 파일의 텍스트 내용
        file_name    : 원본 파일명 (예: "2026-02-02_kdt-backendj-21th.txt")

    Returns:
        run_v7() 결과 dict
    """
    return run_v7(lecture_text=lecture_text, file_name=file_name)


if __name__ == "__main__":
    import argparse
    # ── server.js spawn 연동: python v7_gemini.py <txt경로> ──
    if len(sys.argv) == 2 and sys.argv[1].endswith(".txt") and not any(
        a.startswith("--") for a in sys.argv[1:]
    ):
        txt_path = sys.argv[1]
        try:
            result = run_v7(fname=txt_path)
            print(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(0)

    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=TARGET_FILE)
    args = parser.parse_args()
    run_v7(args.file)