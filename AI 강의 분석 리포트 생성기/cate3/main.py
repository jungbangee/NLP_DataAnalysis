import os
import sys
import json
from pathlib import Path

# cate3 폴더를 sys.path에 추가 (utils, evaluator, prompts 패키지 인식용)
_CATE3_DIR = Path(__file__).parent
if str(_CATE3_DIR) not in sys.path:
    sys.path.insert(0, str(_CATE3_DIR))

from dotenv import load_dotenv

# utils 패키지 로드 (없으면 인라인 대체 함수 사용)
try:
    from utils.evidence_matcher import convert_evidence_list, to_unified_evidence
    from utils.lecture_metadata import resolve_lecture_metadata
except ModuleNotFoundError:
    import re as _re, csv as _csv

    def convert_evidence_list(quotes, script):
        results = []
        script_norm = _re.sub(r'\s+', '', script)
        for q in quotes:
            if not isinstance(q, str):
                q = q.get('quote', '') if isinstance(q, dict) else str(q)
            q_norm = _re.sub(r'\s+', '', q)
            match_type = 'exact' if len(q_norm) >= 4 and q_norm in script_norm else 'none'
            ts_m = _re.search(r'<(\d{2}:\d{2}:\d{2})>', script)
            results.append({'quote': q, 'match_type': match_type,
                           'similarity': 1.0 if match_type=='exact' else 0.0,
                           'timestamp': ts_m.group(1) if ts_m else '', 'source': q})
        return results

    def to_unified_evidence(matched):
        return [{'source': e.get('source', e.get('quote','')),
                 'timestamp': e.get('timestamp','')}
                for e in matched if e.get('match_type') in ('exact','similar')]

    def resolve_lecture_metadata(csv_path, file_stem):
        m = _re.match(r'^(\d{4}-\d{2}-\d{2})_(.+)$', file_stem)
        date      = m.group(1) if m else ''
        course_id = m.group(2) if m else file_stem
        instructor = None
        try:
            with open(csv_path, encoding='utf-8-sig') as f:
                for row in _csv.DictReader(f):
                    if row.get('date')==date and row.get('course_id')==course_id:
                        instructor = row.get('instructor','')
                        break
        except Exception:
            pass
        return {'date': date, 'course_id': course_id, 'instructor': instructor}

from evaluator.gemini_evaluator import GeminiEvaluator
from evaluator.scoring import (
    adjust_score_by_evidence,
    calculate_gemini_score
)
from evaluator.speech_speed import calculate_speech_speed_with_timestamp


# 환경 변수 로드
_CATE3_ENV = Path(__file__).parent / ".env"
load_dotenv(_CATE3_ENV, encoding="utf-8")
API_KEY = (os.getenv("GOOGLE_API_KEY") or
           os.getenv("GEMINI_API_KEY") or
           os.getenv("GCP_API_KEY") or
           "AIzaSyB-ZoAe_gLepBQMoqBxHipAu6Qqyg-bP6U")

# 메타데이터 CSV 경로 (실제 파일명에 맞춰 필요시 수정)
METADATA_CSV_PATH = "강의 메타데이터.csv"

# 이 모듈이 담당하는 카테고리: "3. 개념 설명 명확성"
# Gemini 결과 키 -> 항목 기준표 ID 매핑 (§5 항목 기준표 참조)
ITEM_ID_MAP = {
    "concept_definition": "3.1",
    "example_usage": "3.2",
    "prerequisite_check": "3.3"
}
SPEECH_SPEED_ITEM_ID = "3.4"

# Gemini Evaluator 생성
evaluator = GeminiEvaluator(API_KEY)

NO_FEEDBACK_TEXT = "해당 사항 없음"
FEEDBACK_FIELDS = ("weakness", "suggestion", "example")


def normalize_feedback(score, feedback):
    """
    팀 결정 규칙:
    - score가 5점이면 feedback 전체(weakness/suggestion/example)를
      "해당 사항 없음"으로 통일한다.
    - 5점이 아니더라도, 개별 필드가 비어 있으면(None, "", 누락)
      그 필드만 "해당 사항 없음"으로 채운다.
    """

    if score == 5:
        return {field: NO_FEEDBACK_TEXT for field in FEEDBACK_FIELDS}

    normalized = {}

    for field in FEEDBACK_FIELDS:
        value = feedback.get(field) if feedback else None

        if value is None or (isinstance(value, str) and value.strip() == ""):
            normalized[field] = NO_FEEDBACK_TEXT
        else:
            normalized[field] = value

    return normalized


# 결과 저장 폴더 생성 (스키마 §4: 통일된 결과 폴더)
RESULTS_DIR = Path("results_unified")
RESULTS_DIR.mkdir(exist_ok=True)

# data 폴더 내 txt 파일 조회
lecture_files = list(Path("data").glob("*.txt"))

# 강의별 분석
for lecture_file in lecture_files:

    print(f"\n📖 분석 중: {lecture_file.name}")

    # 강의 로드
    with open(
        lecture_file,
        "r",
        encoding="utf-8"
    ) as f:
        script = f.read()

    # 강의 메타데이터 (date, course_id, instructor) 매칭
    metadata = resolve_lecture_metadata(
        METADATA_CSV_PATH,
        lecture_file.stem
    )

    if metadata["instructor"] is None:
        print(
            f"⚠️  메타데이터 매칭 실패: {lecture_file.name} "
            f"(date={metadata['date']}, course_id={metadata['course_id']})"
        )

    # Gemini 평가
    result = evaluator.evaluate(script)

    # evidence 매칭 (quote -> exact/similar/hallucination 판정, 원문/타임스탬프 포함)
    matched_evidence = {
        "concept_definition": convert_evidence_list(
            result["concept_definition"].get("evidence", []),
            script
        ),
        "example_usage": convert_evidence_list(
            result["example_usage"].get("evidence", []),
            script
        ),
        "prerequisite_check": convert_evidence_list(
            result["prerequisite_check"].get("evidence", []),
            script
        )
    }

    # 디버그용 임시 출력
    print("=== RAW EVIDENCE FROM GEMINI ===")
    print(json.dumps(result["concept_definition"].get("evidence", []), ensure_ascii=False, indent=2))
    print("=== MATCHED EVIDENCE (match_type 포함) ===")
    print(json.dumps(matched_evidence["concept_definition"], ensure_ascii=False, indent=2))

    # 점수 계산 (매칭 결과 전체를 기준으로 hallucination 비율 등을 반영해 보정)
    gemini_scores = calculate_gemini_score(result)

    for key in ("concept_definition", "example_usage", "prerequisite_check"):
        gemini_scores[key] = adjust_score_by_evidence(
            gemini_scores[key],
            matched_evidence[key]
        )

    # 발화 속도 계산 (3.4 - 규칙 기반, evidence는 항상 [])
    speech_result = calculate_speech_speed_with_timestamp(script)

    # 스키마 §1 형식에 맞춘 items 구성
    items = {}

    for result_key, item_id in ITEM_ID_MAP.items():
        score = gemini_scores[result_key]
        items[item_id] = {
            "score": score,
            "reason": result[result_key]["reason"],
            "evidence": to_unified_evidence(matched_evidence[result_key]),
            "feedback": normalize_feedback(
                score,
                result[result_key].get("feedback", {})
            )
        }

    items[SPEECH_SPEED_ITEM_ID] = {
        "score": speech_result["score"],
        "reason": speech_result["reason"],
        "evidence": [],
        "feedback": {}
    }

    # 스키마 §1 최상위 구조
    evaluation_json = {
        "file_name": lecture_file.name,
        "date": metadata["date"],
        "instructor": metadata["instructor"],
        "course_id": metadata["course_id"],
        "items": items
    }

    # 스키마 §4 파일명 규약: {date}_{course_id}_{instructor}.json
    if metadata["date"] and metadata["course_id"] and metadata["instructor"]:
        output_name = (
            f"{metadata['date']}_{metadata['course_id']}_"
            f"{metadata['instructor']}.json"
        )
    else:
        # 메타데이터 매칭에 실패한 경우, 원본 파일명으로 대체하고 경고는 위에서 이미 출력함
        output_name = f"{lecture_file.stem}.json"

    output_path = RESULTS_DIR / output_name

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            evaluation_json,
            f,
            ensure_ascii=False,
            indent=4
        )

    print(
        f"✅ 완료 | "
        f"{output_path}"
    )

print("\n🎉 모든 강의 분석 완료")
print(f"📁 {RESULTS_DIR} 폴더 확인 (대시보드용 통일 스키마)")

if __name__ == "__main__":
    import sys as _sys, io as _io
    _sys.stdout = _io.TextIOWrapper(_sys.stdout.buffer, encoding='utf-8', errors='replace')
    _sys.stderr = _io.TextIOWrapper(_sys.stderr.buffer, encoding='utf-8', errors='replace')
    # ── server.js spawn 연동: python main.py <txt경로> ──
    if len(_sys.argv) == 2 and _sys.argv[1].endswith(".txt") and not any(
        a.startswith("--") for a in _sys.argv[1:]
    ):
        _txt_path = _sys.argv[1]
        try:
            with open(_txt_path, "r", encoding="utf-8") as _f:
                _script = _f.read()
            from pathlib import Path as _Path
            _fname = _Path(_txt_path).name
            _stem  = _Path(_txt_path).stem
            _metadata = resolve_lecture_metadata(METADATA_CSV_PATH, _stem)
            _result   = evaluator.evaluate(_script)
            _matched  = {
                k: convert_evidence_list(_result[k].get("evidence", []), _script)
                for k in ("concept_definition", "example_usage", "prerequisite_check")
            }
            _scores = calculate_gemini_score(_result)
            for _k in ("concept_definition", "example_usage", "prerequisite_check"):
                _scores[_k] = adjust_score_by_evidence(_scores[_k], _matched[_k])
            _speech = calculate_speech_speed_with_timestamp(_script)
            _items = {}
            for _rk, _iid in ITEM_ID_MAP.items():
                _sc = _scores[_rk]
                _items[_iid] = {
                    "score":    _sc,
                    "reason":   _result[_rk]["reason"],
                    "evidence": to_unified_evidence(_matched[_rk]),
                    "feedback": normalize_feedback(_sc, _result[_rk].get("feedback", {}))
                }
            _items[SPEECH_SPEED_ITEM_ID] = {
                "score": _speech["score"], "reason": _speech["reason"],
                "evidence": [], "feedback": {}
            }
            _out = {
                "file_name":  _fname,
                "date":       _metadata["date"],
                "instructor": _metadata["instructor"],
                "course_id":  _metadata["course_id"],
                "items":      _items
            }
            print(json.dumps(_out, ensure_ascii=False))
        except Exception as _e:
            print(json.dumps({"error": str(_e)}, ensure_ascii=False))
        _sys.exit(0)