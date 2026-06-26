"""
instructor_summary.py - 강사 종합 강의평가 생성기 (강사 1명 × 기간 전체)

[목적]
한 강사의 '일자별 요약(daily_summary 출력) N개'를 모아, 강사 단위 종합평가를 만든다.
  1) 정량 집계는 '기계적'으로(카테고리별 평균·표준편차·추세·반복 약점 빈도)
  2) 그 집계 통계 + 대표 일자 샘플을 Gemini에 넘겨
     '역량 프로파일 해석 · 체계적 강약점 · 추세 · 종합 숙련도 등급 · 개발과제 · 타당도 한계'를 서술.

[N(강의 일수)에 견고한 설계 — 15일이든 100일이든 동일하게 동작]
- 반복 약점은 '횟수'가 아니라 '비율(%)'로 집계 → N이 달라도 비교 가능.
- 표본 가드: N<3이면 표준편차 생략, N<5이면 추세 생략(과대해석 방지). 장기 강의는 전반/후반 평균차 병기.
- LLM 입력은 '집계 통계 + 대표 일자 3개(최고/최저/최신)'만 → 토큰·비용이 N에 비례해 늘지 않음.

[참고 프레임워크 — 리포트 해석 근거]
- 다차원 역량(단일점수로 안 뭉갬): Marsh, SEEQ(1982)
- 인지부하·완성예제 효과: Sweller & Cooper(1985), Merrill First Principles(2002)
- 능동학습·상호작용: Chickering & Gamson, Seven Principles(1987)
- 숙련도 4단계 루브릭: Danielson, Framework for Teaching
- 추세/피드백 효과: Hattie, Visible Learning(2009)
- 평가 범위 한계(과정 품질 = L1~2, 학습성과 아님): Kirkpatrick 4단계

입력: results_unified/summary/{date}_{course_id}_{instructor}.json (daily_summary 출력)
출력: results_unified/instructor/{course_id}_{instructor}.json
"""
import json
import os
import statistics as st
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# ── 환경 변수 로드 ────────────────────────────────────────────
_BASE = Path(__file__).parent
load_dotenv(_BASE / ".env", encoding="utf-8")

# ── Gemini 클라이언트 (지연 초기화) ──────────────────────────
MODEL  = "gemini-3.1-pro-preview"
_client = None

_HARDCODED_API_KEY = "AIzaSyB-ZoAe_gLepBQMoqBxHipAu6Qqyg-bP6U"

def get_client():
    global _client
    if _client is None:
        api_key = (os.environ.get("GCP_API_KEY") or
                   os.environ.get("GEMINI_API_KEY") or
                   os.environ.get("GOOGLE_API_KEY") or
                   _HARDCODED_API_KEY)
        _client = genai.Client(api_key=api_key)
    return _client

# ── 경로 설정 ─────────────────────────────────────────────────
ROOT      = _BASE
OUT_DIR   = _BASE / "results_unified" / "instructor"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 상수 (daily_summary.py에서 인라인 복사) ──────────────────
ITEM_NAME = {
    "1.1": "불필요한 반복 표현", "1.2": "발화 완결성", "1.3": "언어 일관성",
    "2.1": "학습목표 안내", "2.2": "전날 복습 연계", "2.3": "설명 순서",
    "2.4": "핵심내용 강조", "2.5": "마무리 요약",
    "3.1": "개념 정의", "3.2": "비유 및 예시 활용", "3.3": "선행개념 확인", "3.4": "발화속도 적절성",
    "4.1": "예시 적절성", "4.2": "실습 연계", "4.3": "오류 대응",
    "5.1": "이해 확인 질문", "5.2": "참여 유도", "5.3": "질문응답 충분성",
}
CATEGORY_NAME = {
    "1": "언어표현 품질", "2": "강의 도입 및 구조", "3": "개념설명 명확성",
    "4": "예시 및 실습 연계", "5": "수강생 상호작용",
}
CATEGORY_ITEMS = {
    "1": ["1.1", "1.2", "1.3"],
    "2": ["2.1", "2.2", "2.3", "2.4", "2.5"],
    "3": ["3.1", "3.2", "3.3", "3.4"],
    "4": ["4.1", "4.2", "4.3"],
    "5": ["5.1", "5.2", "5.3"],
}
ITEM_WEIGHT = {
    "1.1": "높음", "1.2": "중간", "1.3": "중간",
    "2.1": "높음", "2.2": "높음", "2.3": "중간", "2.4": "중간", "2.5": "낮음",
    "3.1": "높음", "3.2": "높음", "3.3": "중간", "3.4": "중간",
    "4.1": "높음", "4.2": "높음", "4.3": "중간",
    "5.1": "높음", "5.2": "높음", "5.3": "높음",
}
WEIGHT_MAP  = {"높음": 3, "중간": 2, "낮음": 1}
GRADE_BANDS = [(85,"우수"),(70,"양호"),(55,"보통"),(40,"미흡"),(0,"부진")]

def grade_for(score_100: int) -> str:
    for lo, g in GRADE_BANDS:
        if score_100 >= lo:
            return g
    return "부진"

MIN_N_SD = 3      # 표준편차 산출 최소 표본
MIN_N_TREND = 5   # 추세 산출 최소 표본

# 강사 숙련도 4단계 (Danielson FfT 매핑) — 일자 요약 평균점수 기준
PROFICIENCY = [(85, "탁월"), (70, "우수"), (55, "평범"), (0, "미흡")]


def proficiency_for(mean_score: float) -> str:
    for lo, g in PROFICIENCY:
        if mean_score >= lo:
            return g
    return "미흡"


# ── 입력 로딩 (MongoDB 기반) ─────────────────────────────────────────
def load_summaries(instructor: str, course_id: str | None = None) -> list[dict]:
    """
    MongoDB categoryresults 컬렉션에서 강사의 강의 데이터를 읽어
    daily_summary 형식의 dict 목록으로 변환합니다.
    """
    from pymongo import MongoClient as _MC
    import os as _os

    mongo_uri = _os.environ.get("MONGO_URI", "mongodb://127.0.0.1:27017/nlp_lecture")
    db_name   = mongo_uri.split("/")[-1].split("?")[0]
    mc        = _MC(mongo_uri)
    db        = mc[db_name]
    col       = db["categoryresults"]

    # 강사 + course_id 필터
    flt = {"instructor": instructor}
    if course_id:
        flt["course_id"] = course_id

    # date+course_id 단위로 그룹핑
    docs = list(col.find(flt).sort("date", 1))
    mc.close()

    grouped: dict[str, dict] = {}
    for d in docs:
        key = f"{d['date']}|{d.get('course_id','')}"
        if key not in grouped:
            grouped[key] = {
                "date":       d["date"],
                "course_id":  d.get("course_id", ""),
                "instructor": d.get("instructor", ""),
                "categories": {},
                "status":     "완료",
            }
        grouped[key]["categories"][d["category"]] = d.get("items", {})

    # daily_summary 형식으로 변환
    summaries = []
    for key, g in sorted(grouped.items()):
        summary = _build_daily_summary_format(g)
        if summary:
            summaries.append(summary)

    return summaries


def _extract_items_flat(categories: dict) -> dict[str, dict]:
    """categories(cate1~cate5) → {item_id: item_val} flat dict"""
    CATE_NUM_MAP = {
        "cate1":{"1":"1.1","2":"1.2","3":"1.3"},
        "cate2":{"1":"2.1","2":"2.2","3":"2.3","4":"2.4","5":"2.5"},
        "cate3":{"1":"3.1","2":"3.2","3":"3.3","4":"3.4"},
        "cate4":{"1":"4.1","2":"4.2","3":"4.3"},
        "cate5":{"1":"5.1","2":"5.2","3":"5.3"},
    }
    flat = {}
    for cate_key, cate_val in categories.items():
        num_map = CATE_NUM_MAP.get(cate_key, {})
        src = cate_val if isinstance(cate_val, dict) else {}
        for item_id, item_val in src.items():
            if not isinstance(item_val, dict):
                continue
            real_id = num_map.get(item_id, item_id)
            score = item_val.get("score") if item_val.get("score") is not None else item_val.get("점수")
            if score is not None:
                flat[real_id] = {"score": float(score), "reason": item_val.get("reason", item_val.get("판정근거",""))}
    return flat


def _build_daily_summary_format(g: dict) -> dict | None:
    """MongoDB 그룹 데이터 → daily_summary.py 출력 형식으로 변환"""
    items_flat = _extract_items_flat(g["categories"])
    if not items_flat:
        return None

    # 카테고리별 가중평균 점수 계산
    cat_scores: dict[str, dict] = {}
    for cat_num, item_ids in CATEGORY_ITEMS.items():
        scores = []
        weights = []
        improvements = []
        for iid in item_ids:
            v = items_flat.get(iid)
            if v is None:
                continue
            s = float(v["score"])
            w = WEIGHT_MAP.get(ITEM_WEIGHT.get(iid, "중간"), 2)
            scores.append(s * w)
            weights.append(w)
            if s < 3.5 and v.get("reason"):
                improvements.append(f"[{iid}] {v['reason'][:60]}")
        if not scores:
            cat_scores[cat_num] = {"score_100": None, "improvements": []}
        else:
            avg_5   = sum(scores) / sum(weights)
            score_100 = round(avg_5 * 20, 1)
            cat_scores[cat_num] = {"score_100": score_100, "improvements": improvements}

    # 종합 점수 (카테고리 단순 평균)
    vals = [v["score_100"] for v in cat_scores.values() if v["score_100"] is not None]
    overall_100 = round(sum(vals) / len(vals), 1) if vals else 0.0
    overall_grade = grade_for(int(overall_100))

    # 완성 여부
    present = sum(1 for v in cat_scores.values() if v["score_100"] is not None)
    status  = "완료" if present == 5 else f"미완({present}/5)"

    # 반복 개선점 수집
    all_improvements = []
    for cv in cat_scores.values():
        all_improvements.extend(cv.get("improvements", []))

    return {
        "date":        g["date"],
        "course_id":   g["course_id"],
        "instructor":  g["instructor"],
        "status":      status,
        "overall": {
            "score_100": overall_100,
            "grade":     overall_grade,
            "rationale": "",   # LLM 판정 없이 기계적 계산
        },
        "categories": {
            cat_num: {
                "score_100": v["score_100"],
                "items":     {iid: items_flat.get(iid, {}) for iid in CATEGORY_ITEMS[cat_num]},
            }
            for cat_num, v in cat_scores.items()
        },
        "improvements":  all_improvements,
        "daily_review":  "",   # instructor_summary에서는 대표일자 샘플로만 사용
    }


# ── 정량 집계 (N에 견고) ─────────────────────────────────────────────
def _trend_slope(ys: list[float]) -> float:
    n = len(ys)
    xs = list(range(n))
    sx, sy = sum(xs), sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys))
    sxx = sum(x * x for x in xs)
    denom = n * sxx - sx * sx
    return (n * sxy - sx * sy) / denom if denom else 0.0


def aggregate(summaries: list[dict]) -> dict:
    n = len(summaries)
    overalls = [s["overall"]["score_100"] for s in summaries]

    # 카테고리별 통계
    cat_stats = {}
    for c in CATEGORY_ITEMS:
        vals = [s["categories"][c]["score_100"] for s in summaries
                if s["categories"].get(c, {}).get("score_100") is not None]
        if not vals:
            cat_stats[c] = {"name": CATEGORY_NAME[c], "mean": None, "n": 0}
            continue
        cat_stats[c] = {
            "name": CATEGORY_NAME[c],
            "mean": round(st.mean(vals), 1),
            "sd": round(st.pstdev(vals), 1) if len(vals) >= MIN_N_SD else None,
            "min": round(min(vals), 1),
            "max": round(max(vals), 1),
            "n": len(vals),
        }

    # 반복 개선점: [X.Y] 태그 빈도 → 비율(%)
    import re
    tag_re = re.compile(r"\[([\d.,\s]+)\]")
    from collections import Counter
    freq = Counter()
    for s in summaries:
        seen = set()
        for imp in s.get("improvements", []):
            for m in tag_re.findall(imp):
                for t in m.split(","):
                    t = t.strip()
                    if t and t not in seen:   # 같은 날 같은 항목 중복 카운트 방지
                        freq[t] += 1
                        seen.add(t)
    recurring = [
        {"item": t, "name": ITEM_NAME.get(t, t), "count": c, "pct": round(100 * c / n, 0)}
        for t, c in freq.most_common(8)
    ]

    # 추세 (N>=5): 기울기 + 전반/후반 평균차
    trend = None
    if n >= MIN_N_TREND:
        slope = _trend_slope(overalls)
        half = n // 2
        first_half = st.mean(overalls[:half])
        second_half = st.mean(overalls[-half:])
        trend = {
            "slope_per_lecture": round(slope, 2),
            "total_change": round(slope * (n - 1), 1),
            "first_half_mean": round(first_half, 1),
            "second_half_mean": round(second_half, 1),
            "half_delta": round(second_half - first_half, 1),
        }

    # 등급 분포 / 결측 일수
    from collections import Counter as C2
    grade_dist = dict(C2(s["overall"]["grade"] for s in summaries))
    partial_days = [s["date"] for s in summaries if not str(s.get("status", "")).startswith("완료")]

    return {
        "n_lectures": n,
        "overall": {
            "mean": round(st.mean(overalls), 1),
            "sd": round(st.pstdev(overalls), 1) if n >= MIN_N_SD else None,
            "min": min(overalls), "max": max(overalls),
        },
        "categories": cat_stats,
        "recurring_weaknesses": recurring,
        "trend": trend,
        "grade_distribution": grade_dist,
        "partial_days": partial_days,
        "date_range": [summaries[0]["date"], summaries[-1]["date"]],
    }


def daily_digest(summaries: list[dict]) -> str:
    """15일 전부를 '한 줄 다이제스트'로(전체 커버리지, 산문 희석 없음).
    형식: 날짜 | 종합 등급 | c1~c5 점수 | 개선태그들"""
    import re
    tag_re = re.compile(r"\[([\d.,\s]+)\]")
    lines = ["[전체 일자 다이제스트]  날짜 | 종합(등급) | c1 c2 c3 c4 c5 | 개선항목"]
    for s in summaries:
        cs = s["categories"]
        sc = " ".join(
            (f"{cs[c]['score_100']:.0f}" if cs.get(c, {}).get("score_100") is not None else "--")
            for c in "12345"
        )
        tags = []
        for imp in s.get("improvements", []):
            for m in tag_re.findall(imp):
                tags += [t.strip() for t in m.split(",") if t.strip()]
        lines.append(
            f"{s['date']} | {s['overall']['score_100']}({s['overall']['grade']}) | {sc} | {','.join(tags)}"
        )
    return "\n".join(lines)


def representative_days(summaries: list[dict]) -> list[dict]:
    """최고·최저·최신 일자(중복 제거). N과 무관하게 최대 3개만 LLM에 전달."""
    by_score = sorted(summaries, key=lambda s: s["overall"]["score_100"])
    picks = {}
    picks[by_score[-1]["date"]] = ("최고", by_score[-1])
    picks[by_score[0]["date"]] = ("최저", by_score[0])
    latest = summaries[-1]
    picks.setdefault(latest["date"], ("최신", latest))
    res = []
    for date, (label, s) in picks.items():
        res.append({
            "label": label, "date": date,
            "score": s["overall"]["score_100"], "grade": s["overall"]["grade"],
            "review": s.get("daily_review", ""),
        })
    return res


# ── LLM 출력 스키마 ──────────────────────────────────────────────────
class InstructorReport(BaseModel):
    proficiency_grade: str = Field(description="강사 숙련도 4단계 중 하나: 탁월/우수/평범/미흡")
    headline: str = Field(description="강사를 한 문장으로 요약한 실행 요약. 핵심 강점과 1순위 개선영역을 담아 1문장.")
    profile_summary: str = Field(description="다차원 역량 프로파일 해석. 강점 영역과 약점 영역을 점수 근거로. 3~4문장.")
    consistency_note: str = Field(description="영역별 일관성(표준편차) 해석. 가장 기복이 큰 영역과 가장 안정적인 영역을 둘 다 SD 수치와 함께 지목. 2문장.")
    trajectory_note: str = Field(description="기간 내 추세 해석(개선/하락/유지). 추세 데이터 없으면 표본 부족임을 명시. 1~2문장.")
    systematic_strengths: list[str] = Field(description="기간 전반에 일관된 강점 2~3개. 각 1문장.")
    systematic_weaknesses: list[str] = Field(description="반복 빈도가 높은 체계적 약점 2~3개. 빈도(%)와 함께. 각 1문장.")
    development_goals: list[str] = Field(description="우선순위 개발과제 정확히 3개. 빈도×중요도 기준 시급한 순. 각 1문장, 구체적 행동.")
    strength_leverage: str = Field(description="강점(개념설명·실습연계 등)을 약점 보완에 어떻게 지렛대로 활용할지 제안. 1~2문장.")
    priority_rationale: str = Field(description="개발과제 3개를 그 순서로 둔 근거(반복 빈도 × 항목 중요도). 1~2문장.")
    validity_caveats: str = Field(description="평가의 타당도 한계(정답셋 부재·STT 기반·과정 품질 한정·부분 데이터 등). 2문장.")


SYSTEM_PROMPT = """\
당신은 IT 부트캠프 강사를 평가하는 교육 전문가입니다.
한 강사의 '여러 강의(일자별 요약)를 집계한 통계'와 '대표 일자 샘플'을 받습니다.
개별 강의가 아니라 '강사의 한 기간 전체'를 평가합니다.

[평가 관점 — 아래 프레임워크에 근거]
- 교수능력은 다차원입니다. 단일 점수로 뭉개지 말고 영역별 강약을 구분하세요. (SEEQ)
- '반복 빈도가 높은' 약점은 우연이 아니라 '체계적' 문제로 다루세요. 특히 완성된 예제 시연 부재는
  초학자의 인지 부하 문제로 해석하세요. (인지부하이론·Worked Example·Merrill)
  ★체계성 임계★: 전체 강의의 40% 이상에서 반복된 항목만 'systematic_weaknesses'(체계적 약점)로 올리세요.
  40% 미만(일회성·산발적)은 체계적 약점으로 격상하지 말고, 필요하면 '간헐적 관찰' 정도로만 언급하세요.
  각 체계적 약점은 빈도가 높은 순으로 제시하세요.
- 수강생 상호작용/능동학습 부족은 핵심 개선 영역으로 봅니다. (Chickering & Gamson 7원칙)
- 숙련도 등급은 4단계(탁월/우수/평범/미흡)로, 제공된 '평균 점수 기준 등급'과 어긋나지 않게. (Danielson)
- 추세(개선/하락)는 코칭 신호로 해석하되, 표본이 적으면 단정하지 마세요. (Hattie)
  ★추세 작성 규칙★: trajectory_note는 (1) 수치 변화를 기술하고 (2) 표본 수를 언급하며
  "단정 어렵다/모니터링 필요"를 명시하세요. 데이터에 없는 '원인'(예: 체력 저하, 긴장감 하락)을
  지어내 단정하지 마세요. 원인을 들 경우 '가능성 중 하나'로만 제시하세요.

[역할 분리 — 필드별 다른 일 (중복 금지)]
- profile_summary: 어느 '영역'이 강하고 약한지 역량 지형도. 구체적 처방·% 나열은 하지 말 것.
- systematic_weaknesses: 약점의 '근거와 패턴'(빈도 % 포함). 처방은 쓰지 말 것.
  각 약점이 위배하는 교육 원리를 한 단어로 명시: 완성예제·설명순서→'인지부하', 상호작용·참여→'능동학습',
  도입·마무리→'구조화'. (간결하게, 과한 학술용어 나열 금지)
- development_goals: '무엇을 어떻게'의 행동 처방. 각 처방 끝에 대상 약점 영역과 빈도를
  괄호로 표기해 추적 가능하게: 예 "...시연하세요. (설명순서 87%)". 패턴 설명은 반복하지 말고 태그만.
- 세 필드에 같은 문장·같은 표현이 반복되면 안 됩니다. 각 칸은 다른 층위의 정보를 담으세요.

[톤 보정 — 숙련도 등급에 맞춰]
- 탁월: 강점 중심 + 소수 심화 보완점. / 우수: 균형(강점 인정 + 개선영역 분명히), 전체에 '탁월/완벽' 최상급 남발 금지.
- 평범: 문제 진단을 분명히 하되 비난조 아닌 개선 지향. / 미흡: 핵심 문제를 직시하되 실행 가능한 출발점 제시.
- (개별 카테고리가 탁월/미흡인 것은 그 영역 한정으로 정확히 표현하되, 강사 '전체'를 등급 이상으로 띄우지 말 것)

[작성 규칙]
- 모든 해석은 제공된 통계 수치에 근거. 수치를 지어내지 마세요.
- systematic_weaknesses에는 제공된 '반복 약점' 비율(%)을 인용하세요.
- development_goals는 정확히 3개, 빈도×중요도가 높은 것부터.
- [필수] validity_caveats에 반드시 포함: 본 평가는 '강의 진행 과정의 품질'(Kirkpatrick L1~2)만 보며
  실제 학습성과(L3~4)는 측정하지 않았고, 검증된 정답 데이터가 없어 점수는 상대·잠정값이라는 점.
  또한 입력에 '부분 데이터(미완) 일자'나 'n이 줄어든 카테고리'가 있으면, 그 날짜/카테고리를
  구체적으로 적어 해당 영역 점수의 표본이 작다는 점을 정량적으로 밝히세요.
"""


def build_llm_input(agg: dict, reps: list[dict], instructor: str,
                    digest: str | None = None) -> str:
    L = [f"[강사] {instructor}  /  강의 {agg['n_lectures']}회  /  기간 {agg['date_range'][0]}~{agg['date_range'][1]}"]
    o = agg["overall"]
    L.append(f"\n[종합점수] 평균 {o['mean']}" + (f" / 표준편차 {o['sd']}" if o['sd'] is not None else " (표본 부족, SD 생략)")
             + f" / 범위 {o['min']}~{o['max']}")
    L.append(f"  평균 기준 숙련도 앵커: {proficiency_for(o['mean'])}")
    L.append(f"  등급 분포: {agg['grade_distribution']}")

    L.append("\n[카테고리별 (평균 / SD / 범위)]")
    for c, cs in agg["categories"].items():
        if cs.get("mean") is None:
            L.append(f"- 카테고리{c} {cs['name']}: 데이터 없음")
        else:
            sd = f"SD {cs['sd']}" if cs.get("sd") is not None else "SD 생략"
            L.append(f"- 카테고리{c} {cs['name']}: 평균 {cs['mean']} / {sd} / {cs['min']}~{cs['max']} (n={cs['n']})")

    L.append("\n[반복 개선점 — 전체 강의 중 비율]")
    for r in agg["recurring_weaknesses"]:
        L.append(f"- [{r['item']}] {r['name']}: {r['count']}회 ({r['pct']:.0f}%)")

    if agg["trend"]:
        t = agg["trend"]
        L.append(f"\n[추세] 기울기 {t['slope_per_lecture']:+}/강의 (전체 {t['total_change']:+}점), "
                 f"전반 평균 {t['first_half_mean']} → 후반 평균 {t['second_half_mean']} (Δ{t['half_delta']:+})")
    else:
        L.append(f"\n[추세] 표본 {agg['n_lectures']}회로 추세 산출 안 함(N<{MIN_N_TREND}).")

    if agg["partial_days"]:
        L.append(f"\n[주의] 부분 데이터(미완) 일자: {', '.join(agg['partial_days'])} — 해당일 점수는 일부 카테고리만 반영됨.")

    if digest:
        L.append("\n" + digest)

    L.append("\n[대표 일자 샘플 (전문)]")
    for r in reps:
        L.append(f"- ({r['label']}) {r['date']} {r['score']}점 [{r['grade']}]: {r['review']}")
    return "\n".join(L)


def summarize_instructor(instructor: str, course_id: str | None = None, save: bool = True,
                         include_digest: bool = False, tag: str = "") -> dict:
    summaries = load_summaries(instructor, course_id)
    if not summaries:
        raise SystemExit(f"일자 요약을 찾을 수 없습니다: instructor={instructor} course={course_id}")

    print(f"\n{'='*60}")
    print(f"  강사 종합평가: {instructor}  (강의 {len(summaries)}회)"
          + (f"  [+전체 다이제스트]" if include_digest else ""))
    print(f"{'='*60}")

    agg = aggregate(summaries)
    reps = representative_days(summaries)
    digest = daily_digest(summaries) if include_digest else None

    print(f"  종합 평균 {agg['overall']['mean']} (SD {agg['overall']['sd']}) / 숙련도 앵커 {proficiency_for(agg['overall']['mean'])}")
    for c, cs in agg["categories"].items():
        if cs.get("mean") is not None:
            print(f"  cat{c} {cs['name']}: {cs['mean']} (SD {cs.get('sd')})")

    llm_input = build_llm_input(agg, reps, instructor, digest)
    response = get_client().models.generate_content(
        model=MODEL,
        contents=llm_input,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=InstructorReport,
            max_output_tokens=8192,
            temperature=0.0,
            seed=42,
            thinking_config=types.ThinkingConfig(thinking_budget=-1),
        ),
    )
    result: InstructorReport = response.parsed
    if result is None:
        result = InstructorReport(**json.loads(response.text))

    # 숙련도 등급 코드 검증/보정 (평균 점수 기준)
    correct = proficiency_for(agg["overall"]["mean"])
    if result.proficiency_grade != correct:
        print(f"  [보정] 숙련도 {result.proficiency_grade}→{correct} (평균 {agg['overall']['mean']} 기준)")
        result.proficiency_grade = correct

    # 구조 무결성 가드
    if len(result.development_goals) != 3:
        print(f"  [경고] 개발과제 {len(result.development_goals)}개 (기대 3)")
    for g in result.development_goals:
        if "(" not in g or ")" not in g:
            print(f"  [경고] 개발과제에 추적태그 누락: {g[:30]}…")
    import re as _g
    for w in result.systematic_weaknesses:
        if not _g.search(r"\d+\s*%", w):
            print(f"  [경고] 체계적 약점에 빈도% 누락: {w[:30]}…")

    # 수치 정합 가드(K1): 서술 인용 %·SD가 실제 통계에 존재하는지 대조
    import re as _re
    narrative = " ".join([
        result.headline, result.profile_summary, result.consistency_note,
        result.trajectory_note, result.strength_leverage,
        *result.systematic_weaknesses, *result.development_goals,
    ])
    pct_set = {int(r["pct"]) for r in agg["recurring_weaknesses"]}
    sd_set = {cs["sd"] for cs in agg["categories"].values() if cs.get("sd") is not None}
    sd_set.add(agg["overall"]["sd"])
    for p in _re.findall(r"(\d+)\s*%", narrative):
        if int(p) not in pct_set:
            print(f"  [정합경고] 출처 불명 % 인용: {p}% (집계 빈도 {sorted(pct_set)})")
    for s in _re.findall(r"(?:SD|표준편차)\s*([\d.]+)", narrative):
        if float(s) not in sd_set:
            print(f"  [정합경고] 출처 불명 SD 인용: {s} (집계 SD {sorted(sd_set)})")

    um = response.usage_metadata
    in_tok = getattr(um, "prompt_token_count", 0) or 0
    out_tok = (getattr(um, "candidates_token_count", 0) or 0) + (getattr(um, "thoughts_token_count", 0) or 0)
    cost = in_tok * 1.25 / 1_000_000 + out_tok * 10.00 / 1_000_000

    # profile_summary 필드 안전 추출 (Gemini가 간혹 키를 빠뜨림)
    profile_summary = getattr(result, 'profile_summary', None) or ''
    if not profile_summary:
        # 결과 dict에서 탐색
        try:
            raw = json.loads(response.text) if result is None else {}
            profile_summary = raw.get('profile_summary', '')
        except Exception:
            profile_summary = ''

    output = {
        "instructor": instructor,
        "course_id": course_id or summaries[0].get("course_id"),
        "n_lectures": agg["n_lectures"],
        "date_range": agg["date_range"],
        "proficiency_grade": result.proficiency_grade,
        "headline": result.headline,
        "stats": {
            "overall": agg["overall"],
            "categories": agg["categories"],
            "ranked_categories": [
                {"rank": i + 1, "category": c, "name": cs["name"],
                 "mean": cs["mean"], "sd": cs.get("sd"), "tier": proficiency_for(cs["mean"])}
                for i, (c, cs) in enumerate(
                    sorted(((c, cs) for c, cs in agg["categories"].items() if cs.get("mean") is not None),
                           key=lambda kv: kv[1]["mean"], reverse=True))
            ],
            "trend": agg["trend"],
            "grade_distribution": agg["grade_distribution"],
            "recurring_weaknesses": agg["recurring_weaknesses"],
            "partial_days": agg["partial_days"],
        },
        "profile_summary": profile_summary,
        "consistency_note": result.consistency_note,
        "trajectory_note": result.trajectory_note,
        "systematic_strengths": result.systematic_strengths,
        "systematic_weaknesses": result.systematic_weaknesses,
        "development_goals": result.development_goals,
        "priority_rationale": result.priority_rationale,
        "strength_leverage": result.strength_leverage,
        "validity_caveats": result.validity_caveats,
        "model": MODEL,
        "tokens": {"input": in_tok, "output": out_tok},
        "cost_usd": round(cost, 5),
    }

    print(f"\n{'─'*60}")
    print(f"  숙련도: {result.proficiency_grade}  / 종합평균 {agg['overall']['mean']}")
    print(f"  토큰: 입력 {in_tok:,} / 출력 {out_tok:,}  비용 ${cost:.5f}")

    if save:
        course = output["course_id"] or "unknown"
        out_path = OUT_DIR / f"{course}_{instructor}{tag}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"  저장: {out_path}")
    print(f"{'─'*60}")
    return output


if __name__ == "__main__":
    import argparse
    import io as _io
    # Windows에서 stdout을 utf-8로 강제 (server.js spawn 연동 시 한글 깨짐 방지)
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    # server.js spawn 연동: python instructor_summary.py --instructor 김영아
    # argparse보다 먼저 처리해야 unrecognized arguments 방지
    _args_raw = sys.argv[1:]
    if _args_raw and not any(a.startswith("--") for a in _args_raw):
        # positional 인자로 넘어온 경우 (예외 처리)
        pass

    parser = argparse.ArgumentParser(description="강사 종합 강의평가 생성기")
    parser.add_argument("--instructor", required=True, help="강사명 (예: 김영아)")
    parser.add_argument("--course",     default=None,  help="course_id로 한정(선택)")
    args = parser.parse_args()

    result = summarize_instructor(args.instructor, args.course)
    # server.js가 JSON.parse()로 수신할 수 있도록 stdout으로 출력
    print(json.dumps(result, ensure_ascii=False))