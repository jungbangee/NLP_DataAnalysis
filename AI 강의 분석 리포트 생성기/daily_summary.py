"""
daily_summary.py - 일자(강의 1개)별 요약 생성기

[목적]
강의 하루치 = 5개 카테고리 통일 JSON을 입력받아,
  1) 카테고리별 점수(항목 가중평균, 0~5 / 0~100)를 '기계적'으로 산출하고
  2) 그 점수 + 항목 reason/약점을 Gemini 3.1 Pro에 넘겨
     '종합점수·등급·그날 총평·강점·개선점'을 LLM이 직접 판정하게 한다.
강의 1개 → 요약 1개. 출력: results_unified/summary/{date}_{course_id}_{instructor}.json

[설계 결정 - daily-summary-design 메모]
- 카테고리 점수 = 항목 가중평균(높음3/중간2/낮음1). (확정)
- 종합점수·카테고리 가중은 고정 수치 없이 LLM 판단에 위임. (사용자 결정)
- 결측 카테고리는 있는 것만 산출 + status="미완(N/5)". (김영아는 5/5 완비)
- 전체 스크립트는 LLM에 넣지 않음(카테고리 점수 + 항목 근거/약점만). temp=0.

[입력 위치 - 카테고리별 산출 파일이 흩어져 있음]
  cat2  : results_unified/{date}_{course_id}_{instructor}.json   (items 2.x)
  cat1+5: results_unified/cate15/{date}_{course_id}_report.json  (items 1.x, 5.x)
  cat3  : results_unified/cate3/{date}_{course_id}_{instructor}.json (items 3.x)
  cat4  : results_unified/cate4/{date}_{course_id}_{instructor}.json (items 4.x)
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

_BASE = Path(__file__).parent
sys.path.insert(0, str(_BASE))
sys.path.insert(0, str(_BASE.parent))

load_dotenv(_BASE / ".env", encoding="utf-8")

ROOT    = _BASE
UNIFIED = ROOT / "results_unified"
OUT_DIR = UNIFIED / "summary"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL    = "gemini-3.1-pro-preview"
_HARDCODED_API_KEY = "AIzaSyB-ZoAe_gLepBQMoqBxHipAu6Qqyg-bP6U"
_client  = None

def get_client():
    global _client
    if _client is None:
        api_key = (os.environ.get("GCP_API_KEY") or
                   os.environ.get("GEMINI_API_KEY") or
                   os.environ.get("GOOGLE_API_KEY") or
                   _HARDCODED_API_KEY)
        _client = genai.Client(api_key=api_key)
    return _client

# 하위 호환: client.models.generate_content(...) → get_client().models.generate_content(...)
class _ClientProxy:
    def __getattr__(self, name):
        return getattr(get_client(), name)
client = _ClientProxy()

# ── 항목 중요도 → 가중치 (전 18개 항목, 기획서 requirements.md 기준) ──────
WEIGHT_MAP = {"높음": 3, "중간": 2, "낮음": 1}
ITEM_WEIGHT = {
    "1.1": "높음", "1.2": "중간", "1.3": "중간",
    "2.1": "높음", "2.2": "높음", "2.3": "중간", "2.4": "중간", "2.5": "낮음",
    "3.1": "높음", "3.2": "높음", "3.3": "중간", "3.4": "중간",
    "4.1": "높음", "4.2": "높음", "4.3": "중간",
    "5.1": "높음", "5.2": "높음", "5.3": "높음",
}
ITEM_NAME = {
    "1.1": "불필요한 반복 표현", "1.2": "발화 완결성", "1.3": "언어 일관성",
    "2.1": "학습목표 안내", "2.2": "전날 복습 연계", "2.3": "설명 순서",
    "2.4": "핵심내용 강조", "2.5": "마무리 요약",
    "3.1": "개념 정의", "3.2": "비유 및 예시 활용", "3.3": "선행개념 확인", "3.4": "발화속도 적절성",
    "4.1": "예시 적절성", "4.2": "실습 연계", "4.3": "오류 대응",
    "5.1": "이해 확인 질문", "5.2": "참여 유도", "5.3": "질문응답 충분성",
}
CATEGORY_NAME = {
    "1": "언어표현 품질",
    "2": "강의 도입 및 구조",
    "3": "개념설명 명확성",
    "4": "예시 및 실습 연계",
    "5": "수강생 상호작용",
}
# 카테고리별 기대 항목 수 (결측 판정용)
CATEGORY_ITEMS = {
    "1": ["1.1", "1.2", "1.3"],
    "2": ["2.1", "2.2", "2.3", "2.4", "2.5"],
    "3": ["3.1", "3.2", "3.3", "3.4"],
    "4": ["4.1", "4.2", "4.3"],
    "5": ["5.1", "5.2", "5.3"],
}
# 카테고리 중요도(종합 앵커 계산용 참고치). 기획서: 카테고리1=중, 2~5=상.
# 고정 가중치가 아니라 LLM 종합점수의 '참고 앵커'를 만드는 데만 쓴다.
CATEGORY_WEIGHT = {"1": 2, "2": 3, "3": 3, "4": 3, "5": 3}


# 종합점수 → 등급 구간 (코드 레벨 강제 검증용)
GRADE_BANDS = [(85, "우수"), (70, "양호"), (55, "보통"), (40, "미흡"), (0, "부진")]


def grade_for(score_100: int) -> str:
    for lo, g in GRADE_BANDS:
        if score_100 >= lo:
            return g
    return "부진"


def reference_anchors(categories: dict) -> dict:
    """종합점수 참고 앵커: 카테고리 100점들의 단순평균 / 중요도 가중평균."""
    vals = [(c, categories[c]["score_100"]) for c in categories if categories[c]["score_100"] is not None]
    if not vals:
        return {"simple": None, "weighted": None}
    simple = sum(v for _, v in vals) / len(vals)
    tw = sum(CATEGORY_WEIGHT[c] for c, _ in vals)
    weighted = sum(v * CATEGORY_WEIGHT[c] for c, v in vals) / tw
    return {"simple": round(simple, 1), "weighted": round(weighted, 1)}


# ── LLM 출력 스키마 ──────────────────────────────────────────────────
class Overall(BaseModel):
    score_100: int = Field(description="이 강의의 종합 점수 0~100 정수. 카테고리 점수와 항목 근거를 종합해 직접 판정.")
    grade: str = Field(description="5단계 등급 중 하나: 우수/양호/보통/미흡/부진")
    rationale: str = Field(description="종합점수·등급을 그렇게 준 근거. 어떤 카테고리를 더 무겁게 봤는지 포함. 2~3문장.")


class CategoryComment(BaseModel):
    category: str = Field(description="카테고리 번호 '1'~'5' 중 하나")
    comment: str = Field(description="해당 카테고리 점수를 근거로 한 한줄평. 1문장, 40자 내외.")


class DailySummary(BaseModel):
    overall: Overall
    category_comments: list[CategoryComment] = Field(
        description="카테고리1~5 각각의 한줄평. 5개 모두 작성(데이터 없는 카테고리는 제외).")
    daily_review: str = Field(description="그날 강의 총평. 잘된 흐름과 아쉬운 흐름을 엮어 3~5문장. 강사가 읽을 글.")
    strengths: list[str] = Field(
        description="이날 강의의 강점 정확히 3개. 각 1문장. 문장 끝에 근거 항목 태그 [X.Y] 부착.")
    improvements: list[str] = Field(
        description="이날 강의의 개선점 정확히 3개. 각 1문장, 구체적 행동 지침. 문장 끝에 근거 항목 태그 [X.Y] 부착.")


# ── 입력 로딩 ────────────────────────────────────────────────────────
def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_day(date: str, course_id: str, instructor: str) -> tuple[dict, dict]:
    """MongoDB categoryresults에서 해당 강의 데이터를 읽어 items 반환.

    returns (meta, items) — items = {"1.1": {score,reason,feedback,...}, ...}
    """
    from pymongo import MongoClient as _MC

    CATE_NUM_MAP = {
        "cate1":{"1":"1.1","2":"1.2","3":"1.3"},
        "cate2":{"1":"2.1","2":"2.2","3":"2.3","4":"2.4","5":"2.5"},
        "cate3":{"1":"3.1","2":"3.2","3":"3.3","4":"3.4"},
        "cate4":{"1":"4.1","2":"4.2","3":"4.3"},
        "cate5":{"1":"5.1","2":"5.2","3":"5.3"},
    }

    mongo_uri = os.environ.get("MONGO_URI", "mongodb://127.0.0.1:27017/nlp_lecture")
    db_name   = mongo_uri.split("/")[-1].split("?")[0]
    mc        = _MC(mongo_uri)
    db        = mc[db_name]
    col       = db["categoryresults"]

    docs = list(col.find({"date": date, "course_id": course_id}))
    mc.close()

    items: dict[str, dict] = {}
    meta = {"date": date, "course_id": course_id, "instructor": instructor}

    for d in docs:
        cate_key = d.get("category", "")
        num_map  = CATE_NUM_MAP.get(cate_key, {})
        src      = d.get("items", {})
        for item_id, item_val in src.items():
            if not isinstance(item_val, dict):
                continue
            real_id = num_map.get(item_id, item_id)
            score   = item_val.get("score") if item_val.get("score") is not None else item_val.get("점수")
            if score is not None:
                items[real_id] = {
                    "score":    float(score),
                    "reason":   item_val.get("reason", item_val.get("판정근거", "")),
                    "feedback": item_val.get("feedback", {}),
                    "evidence": item_val.get("evidence", []),
                }

    if not docs:
        print(f"  [경고] MongoDB에서 데이터 없음: date={date}, course_id={course_id}")

    return meta, items


# ── 카테고리 점수(기계적 가중평균) ──────────────────────────────────────
def category_scores(items: dict) -> tuple[dict, str]:
    """카테고리별 가중평균 점수(0~5)/100점 환산. 있는 항목만 사용.

    returns (categories, status). status = "완료(5/5)" 또는 "미완(N/5)"
    """
    categories = {}
    present = 0
    for cat, ids in CATEGORY_ITEMS.items():
        have = [i for i in ids if i in items]
        if not have:
            categories[cat] = {
                "name": CATEGORY_NAME[cat], "score": None, "score_100": None,
                "items_present": 0, "items_total": len(ids),
            }
            continue
        present += 1
        tw = sum(WEIGHT_MAP[ITEM_WEIGHT[i]] for i in have)
        score = sum(items[i]["score"] * WEIGHT_MAP[ITEM_WEIGHT[i]] for i in have) / tw
        categories[cat] = {
            "name": CATEGORY_NAME[cat],
            "score": round(score, 3),
            "score_100": round(score * 20, 1),
            "items_present": len(have),
            "items_total": len(ids),
        }
    status = f"{'완료' if present == 5 else '미완'}({present}/5)"
    return categories, status


# ── LLM 입력 텍스트 구성 (전체 스크립트 X) ──────────────────────────────
def build_llm_input(categories: dict, items: dict, anchors: dict, status: str) -> str:
    lines = []
    if not status.startswith("완료"):
        present = [c for c in categories if categories[c]["score"] is not None]
        lines.append(
            f"[주의] 이 강의는 5개 카테고리 중 일부만 채점됨(상태 {status}). "
            f"채점된 카테고리({', '.join(present)})만 근거로 종합을 산출하고, "
            f"rationale에 '일부 영역만 평가된 부분 결과'임을 한 문장으로 밝히세요.\n"
        )
    lines.append("[카테고리별 점수 (항목 가중평균, 0~5 / 0~100)]")
    for cat, c in categories.items():
        if c["score"] is None:
            lines.append(f"- 카테고리{cat} {c['name']}: (데이터 없음)")
        else:
            lines.append(f"- 카테고리{cat} {c['name']}: {c['score']:.2f}/5 ({c['score_100']:.0f}/100)")

    if anchors["weighted"] is not None:
        lines.append(
            f"\n[종합점수 참고 앵커]\n"
            f"- 단순평균: {anchors['simple']:.0f}/100\n"
            f"- 중요도 가중평균(카테고리1=중,2~5=상): {anchors['weighted']:.0f}/100\n"
            f"  ※ 앵커는 참고용입니다. 종합점수는 가중평균 근처에서 시작하되, "
            f"항목 근거를 보고 ±조정할 수 있습니다. 앵커에서 5점 넘게 벗어나면 그 이유를 rationale에 밝히세요."
        )

    lines.append("\n[항목별 점수·근거·약점·채점기 제안]")
    for item_id in sorted(items.keys()):
        it = items[item_id]
        name = ITEM_NAME.get(item_id, item_id)
        weight = ITEM_WEIGHT.get(item_id, "?")
        fb = it.get("feedback") or {}
        weakness = fb.get("weakness", "")
        suggestion = fb.get("suggestion", "")
        reason = it.get("reason", "")
        block = (
            f"- {item_id} {name} (중요도 {weight}) : {it.get('score')}점\n"
            f"    근거: {reason}\n"
            f"    약점: {weakness}"
        )
        if suggestion and suggestion not in ("현 수준 유지", ""):
            block += f"\n    채점기 제안: {suggestion}"
        ev = it.get("evidence") or []
        if ev:
            q = (ev[0].get("source") or "").strip()
            if q:
                block += f"\n    실제 발화 예: \"{q[:80]}\""
        lines.append(block)
    return "\n".join(lines)


SYSTEM_PROMPT = """\
당신은 IT 부트캠프 강의 품질을 평가하는 교육 전문가입니다.
한 강사의 '하루치 강의 한 개'에 대한 5개 카테고리 점수와 세부 항목 근거를 받습니다.

[당신의 일]
- 카테고리 점수와 항목 근거를 종합해 이 강의의 '종합 점수(0~100)'와 '등급'을 직접 판정합니다.
- 제공된 '종합점수 참고 앵커'(단순평균·가중평균)를 출발점으로 삼으세요. 가중평균 앵커 근처에서
  시작하되, 어떤 영역이 그날 강의의 질을 더 좌우했는지 항목 근거를 보고 ±조정할 수 있습니다.
  앵커에서 5점 넘게 벗어나면 그 이유를 rationale에 반드시 밝히세요.
- 등급은 정확히 다음 5단계 중 하나: 우수(85~100) / 양호(70~84) / 보통(55~69) / 미흡(40~54) / 부진(0~39).
  score_100과 등급 구간이 어긋나지 않게 하세요.

[category_comments — 카테고리별 한줄평]
- 각 카테고리(1~5)마다 그 점수를 근거로 한 줄평을 답니다. 점수가 높으면 무엇이 좋았는지,
  낮으면 무엇이 부족한지 한 문장(40자 내외)으로. 데이터 없는 카테고리는 제외.

[역할 분리 — 세 필드는 서로 다른 일을 합니다 (중복 금지)]
- daily_review: 그날 강의를 '한 발 물러서서' 본 서술형 총평. 정확히 4문장, 다음 구조를 따르세요.
    1문장: 그날 강의의 전반적 인상.
    2문장: 가장 두드러진 강점(흐름 중심, 항목 나열 금지).
    3문장: 가장 아쉬운 약점(흐름 중심).
    4문장: 강사에게 주는 핵심 제언 한 가지.
  strengths/improvements에 적을 세부 항목을 여기서 똑같이 반복하지 마세요.
- strengths: daily_review에서 다 말하지 않은 '구체적' 강점 정확히 3개. 각 1문장.
- improvements: daily_review와 겹치지 않는 '구체적' 개선점 정확히 3개. 각 1문장.
  ★우선순위 정렬★: 점수가 가장 낮은 항목/카테고리부터 먼저 오도록 '시급한 순서'로 나열하세요.
  첫 번째 개선점은 그날 가장 점수가 낮은 영역을 반드시 다뤄야 합니다.
- 세 필드를 다 읽었을 때 같은 문장·같은 지적이 반복되면 안 됩니다. 각 칸은 새로운 정보를 더해야 합니다.
- strengths/improvements 각 문장 끝에는 근거가 된 항목 번호를 대괄호로 답니다. 예: "...각인시켰습니다. [2.4]"
  근거가 둘이면 [3.1, 3.2]처럼. daily_review에는 태그를 달지 마세요.

[공통 작성 규칙]
- 막연한 칭찬·지적 금지. 모두 위 항목 점수·근거에 기반.
- 항목별 '채점기 제안'이 있으면 참고해 improvements를 더 구체화하되, 그대로 베끼지 말고
  그날 강의 맥락에 맞게 한 문장으로 다듬으세요.
- 강사의 실제 발화를 인용할 때는 반드시 큰따옴표("...")로 감싸 문장에 자연스럽게 넣으세요.
  제공된 '실제 발화 예'에 없는 말을 강사가 한 것처럼 지어내 인용하지 마세요.
- 점수가 낮은 항목은 improvements로, 높은 항목은 strengths로.
- improvements는 '무엇을 어떻게'가 드러나는 구체적 행동 지침으로.
- 제공된 점수·근거 외의 사실을 지어내지 마세요. 전체 강의 스크립트는 제공되지 않습니다.

[톤 보정 — 종합 등급에 맞춰 daily_review의 어조를 조절]
- 우수: 강점 위주로 서술하되 1가지 보완점 언급.
- 양호/보통: 균형 잡힌 어조. "매우 훌륭/완벽" 같은 최상급 표현을 강의 전체에 붙이지 말 것.
  잘된 점 1~2가지와 아쉬운 점 1~2가지를 비등하게 다루세요.
- 미흡/부진: 문제 진단을 분명히 하되 비난조가 아닌 개선 지향으로.

[자기검증 — 출력 전 반드시 확인]
- score_100과 grade의 구간이 일치하는가? (우수85+/양호70+/보통55+/미흡40+/부진0+)
- 가장 점수가 낮은 카테고리가 improvements 또는 daily_review에서 다뤄졌는가?
- 세 필드(review/strengths/improvements)에 같은 지적이 그대로 반복되지 않는가?
"""


def summarize_day(date: str, course_id: str, instructor: str, save: bool = True) -> dict:
    print(f"\n{'='*60}")
    print(f"  일자 요약 생성: {date} / {course_id} / {instructor}")
    print(f"  모델: {MODEL} (종합점수·등급·총평은 LLM 판정)")
    print(f"{'='*60}")

    meta, items = load_day(date, course_id, instructor)
    if not items:
        raise SystemExit(f"입력 항목이 하나도 없습니다: {date}_{course_id}_{instructor}")

    categories, status = category_scores(items)
    for cat, c in categories.items():
        s = "데이터 없음" if c["score"] is None else f"{c['score']:.2f}/5 ({c['score_100']:.0f}/100)"
        print(f"  카테고리{cat} {c['name']}: {s}")
    print(f"  상태: {status}  / 항목 {len(items)}개")

    anchors = reference_anchors(categories)
    print(f"  앵커: 단순 {anchors['simple']} / 가중 {anchors['weighted']}")
    llm_input = build_llm_input(categories, items, anchors, status)
    response = client.models.generate_content(
        model=MODEL,
        contents=llm_input,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=DailySummary,
            max_output_tokens=8192,
            temperature=0.0,
            seed=42,  # 재현성: temp=0 + 동적 thinking의 run간 변동을 시드로 고정
            thinking_config=types.ThinkingConfig(thinking_budget=-1),
        ),
    )
    result: DailySummary = response.parsed
    if result is None:
        result = DailySummary(**json.loads(response.text))

    # 토큰·비용 집계 (Gemini 3.1 Pro 추정 단가, GCP 크레딧 차감)
    um = response.usage_metadata
    in_tok = getattr(um, "prompt_token_count", 0) or 0
    out_tok = (getattr(um, "candidates_token_count", 0) or 0) + (getattr(um, "thoughts_token_count", 0) or 0)
    cost = in_tok * 1.25 / 1_000_000 + out_tok * 10.00 / 1_000_000

    # 카테고리 한줄평을 categories에 병합
    for cc in result.category_comments:
        if cc.category in categories:
            categories[cc.category]["comment"] = cc.comment

    # 등급 코드 레벨 강제 검증/보정 (LLM 등급이 점수 구간과 어긋나면 점수 기준으로 교정)
    correct_grade = grade_for(result.overall.score_100)
    if result.overall.grade != correct_grade:
        print(f"  [보정] 등급 {result.overall.grade}→{correct_grade} (점수 {result.overall.score_100} 기준)")
        result.overall.grade = correct_grade

    if len(result.strengths) != 3 or len(result.improvements) != 3:
        print(f"  [경고] 강점 {len(result.strengths)}개 / 개선점 {len(result.improvements)}개 (기대 3/3)")

    n_sent = len([s for s in result.daily_review.replace("!", ".").replace("?", ".").split(".") if s.strip()])
    if n_sent != 4:
        print(f"  [경고] daily_review 문장 수 {n_sent} (기대 4)")

    # 태그 기반 정합 검증: 강점은 고점(≥4) 항목, 개선점은 저점(≤3) 항목을 근거로 해야 함
    tag_re = __import__("re").compile(r"\[([\d.,\s]+)\]")
    def _tagged_ids(text):
        ids = []
        for m in tag_re.findall(text):
            ids += [t.strip() for t in m.split(",") if t.strip()]
        return ids
    for s in result.strengths:
        for i in _tagged_ids(s):
            if i in items and items[i]["score"] <= 3:
                print(f"  [정합경고] 강점이 저점 항목 인용: {i}={items[i]['score']}점")
    for s in result.improvements:
        for i in _tagged_ids(s):
            if i in items and items[i]["score"] >= 4:
                print(f"  [정합경고] 개선점이 고점 항목 인용: {i}={items[i]['score']}점")

    output = {
        "file_name": f"{date}_{course_id}_{instructor}.json",
        "date": date,
        "instructor": instructor,
        "course_id": course_id,
        "status": status,
        "categories": categories,
        "anchors": anchors,
        "overall": {
            "score_100": result.overall.score_100,
            "grade": result.overall.grade,
            "rationale": result.overall.rationale,
        },
        "daily_review": result.daily_review,
        "strengths": result.strengths,
        "improvements": result.improvements,
        "model": MODEL,
        "tokens": {"input": in_tok, "output": out_tok},
        "cost_usd": round(cost, 5),
    }

    print(f"\n{'─'*60}")
    print(f"  종합: {output['overall']['score_100']}/100  [{output['overall']['grade']}]")
    print(f"  토큰: 입력 {in_tok:,} / 출력 {out_tok:,}  비용 ${cost:.5f}")
    print(f"  총평: {output['daily_review'][:80]}...")

    if save:
        out_path = OUT_DIR / f"{date}_{course_id}_{instructor}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"  저장: {out_path}")
    print(f"{'─'*60}")
    return output


if __name__ == "__main__":
    import argparse
    import io as _io
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description="일자별 강의 요약 생성기")
    parser.add_argument("--date", help="YYYY-MM-DD")
    parser.add_argument("--course", default="kdt-backendj-21th")
    parser.add_argument("--instructor", default="김영아")
    parser.add_argument("--test", action="store_true", help="김영아 02-02~02-04 3개 테스트")
    args = parser.parse_args()

    if args.test:
        for d in ["2026-02-02", "2026-02-03", "2026-02-04"]:
            summarize_day(d, args.course, args.instructor)
    elif args.date:
        result = summarize_day(args.date, args.course, args.instructor)
        print(json.dumps(result, ensure_ascii=False))
    else:
        parser.error("--date 또는 --test 중 하나는 필요합니다")