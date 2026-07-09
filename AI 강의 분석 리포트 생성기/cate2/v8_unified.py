"""
v8_unified.py - 카테고리 2 채점 → 통일 스키마 JSON 출력

[v8 특징 — v7 대비]
- 출력을 팀 통일 스키마(결과_JSON_스키마_명세.md)로 변환:
    {file_name, date, instructor, course_id, items: {"2.x": {score, reason, evidence:[{source,timestamp}], feedback}}}
- 원문 대조(exact/fuzzy/none)는 v7 그대로 '항상 수행'하되, evidence에는 'exact만' 첨부
- 채점 엔진(Gemini 3.1 Pro, temp=0, 가드, 전체구간 샘플링)은 v7_gemini를 import해 재사용
- 메타데이터(date/course_id/instructor)는 파일명 + 강의 메타데이터.csv에서 추출

* v8 범위: 카테고리 2(2.1~2.5)만. 타 카테고리는 팀원 코드가 같은 스키마로 산출.
"""
import json
import csv
import sys
from pathlib import Path

from dotenv import load_dotenv

# cate2 폴더 자체를 경로에 추가 (scoring 패키지 인식용)
_CATE2_DIR = Path(__file__).parent
sys.path.insert(0, str(_CATE2_DIR))
sys.path.insert(0, str(_CATE2_DIR.parent))

# v7 채점 엔진 재사용 (원문 대조 로직 포함)
from v7_gemini import score_item, build_utt_index, _normalize, MODEL
from utils import parse_file, extract_opening, extract_closing, extract_full
from rubrics import CATEGORY2_ITEMS

load_dotenv(Path(__file__).parent / ".env", encoding="utf-8")

TARGET_FILE = "2026-02-02_kdt-backendj-21th.txt"
OUT_DIR = Path(__file__).parent.parent / "results_unified"
OUT_DIR.mkdir(parents=True, exist_ok=True)
META_CSV = Path(__file__).parent.parent / "강의 메타데이터.csv"


def parse_meta(fname: str) -> tuple[str, str, str]:
    """파일명 + 메타 CSV에서 date, course_id, instructor 추출.
    파일명 형식: {date}_{course_id}.txt  예) 2026-02-02_kdt-backendj-21th.txt"""
    base = fname[:-4] if fname.endswith(".txt") else fname
    date, course_id = base.split("_", 1)
    instructor = ""
    if META_CSV.exists():
        # utf-8-sig: 엑셀 저장 CSV의 BOM 제거 (첫 열 키 깨짐 방지)
        with open(META_CSV, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("date") == date and row.get("course_id") == course_id:
                    instructor = row.get("instructor", "")
                    break
    return date, course_id, instructor


def run_v8(fname: str = TARGET_FILE, src_dir: str | None = None,
           lecture_text: str = "", file_name: str = "") -> dict:
    """
    두 가지 방식으로 호출 가능합니다.

    1. 로컬 파일:  run_v8(fname="2026-02-02_강의.txt")
    2. 웹 업로드:  run_v8(lecture_text="...", file_name="2026-02-02_강의.txt")
    """
    from pathlib import Path as _P
    actual_fname = file_name or fname
    # 전체 경로가 들어와도 파일명만 파싱에 사용
    _basename = _P(actual_fname).name
    date, course_id, instructor = parse_meta(_basename)
    # actual_fname은 파일 읽기용으로 전체 경로 유지

    print(f"\n{'='*60}")
    print(f"  v8 통일스키마 채점: {actual_fname}")
    print(f"  date={date} / course_id={course_id} / instructor={instructor or '(미확인)'}")
    print(f"  모델: {MODEL} / 카테고리 2 / 원문 대조: 항상 수행(출력은 exact만)")
    print(f"{'='*60}")

    if lecture_text:
        lines = [l.strip() for l in lecture_text.splitlines() if l.strip()]
        print(f"  업로드 텍스트 로드: {len(lines)}줄")
    else:
        # 전체 경로가 넘어온 경우 그대로 사용, 파일명만인 경우 src_dir 조합
        _p = Path(fname)
        if _p.is_absolute() and _p.exists():
            src = str(_p)
        elif src_dir is not None:
            src = str(Path(src_dir) / fname)
        else:
            src = fname
        lines = parse_file(src)
    utt_index = build_utt_index(lines)
    source_norm = _normalize(" ".join(u["text"] for u in utt_index))

    segments = {
        "2.1": extract_opening(lines, minutes=10),
        "2.2": extract_opening(lines, minutes=15),
        "2.3": extract_full(lines),
        "2.4": extract_full(lines),
        "2.5": extract_closing(lines, minutes=30),
    }

    items = {}
    match_stats = {"exact": 0, "fuzzy": 0, "none": 0}

    for item in CATEGORY2_ITEMS:
        item_id = item["id"]
        print(f"\n  [{item_id}] {item['name']} 채점 중...", end="", flush=True)
        r = score_item(item_id, segments[item_id], source_norm, utt_index)

        # 원문 대조 결과 집계 (검증 과정은 score_item 내부에서 항상 수행됨)
        for e in r["evidence"]:
            match_stats[e["match_type"]] += 1

        # 출력 evidence: exact 매칭만, {source, timestamp}로 변환
        exact_ev = [
            {"source": e["source"], "timestamp": e["timestamp"]}
            for e in r["evidence"] if e["match_type"] == "exact"
        ]

        items[item_id] = {
            "score": r["score"],
            "reason": r["reason"],
            "evidence": exact_ev,        # 항상 배열, exact만
            "feedback": r["feedback"],   # {weakness, suggestion, example}
        }

        n_total = len(r["evidence"])
        n_exact = len(exact_ev)
        print(f" {r['score']}/5  (인용 {n_total}개 중 exact {n_exact}개 채택)")

    output = {
        "file_name": fname,
        "date": date,
        "instructor": instructor,
        "course_id": course_id,
        "items": items,
    }

    # 로컬 파일 방식일 때만 저장
    if not lecture_text:
        safe_instr = instructor or "unknown"
        out_path = OUT_DIR / f"{date}_{course_id}_{safe_instr}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'─'*60}")
    print(f"  원문 대조 결과(검증 수행 증빙): "
          f"exact {match_stats['exact']} / fuzzy {match_stats['fuzzy']} / none {match_stats['none']}")
    print(f"  → 출력 evidence에는 exact {match_stats['exact']}개만 첨부")
    if not lecture_text:
        print(f"  결과 저장: {out_path}")
    print(f"{'─'*60}")
    return output


def analyze_from_upload(lecture_text: str, file_name: str) -> dict:
    """
    웹에서 업로드된 txt 파일을 카테고리 2 채점 후 통일 스키마로 반환합니다.

    Args:
        lecture_text : 업로드된 파일의 텍스트 내용
        file_name    : 원본 파일명 (예: "2026-02-02_kdt-backendj-21th.txt")

    Returns:
        run_v8() 결과 dict (통일 스키마)
    """
    return run_v8(lecture_text=lecture_text, file_name=file_name)


if __name__ == "__main__":
    import argparse
    # ── server.js spawn 연동: python v8_unified.py <txt경로> ──
    if len(sys.argv) == 2 and sys.argv[1].endswith(".txt") and not any(
        a.startswith("--") for a in sys.argv[1:]
    ):
        from pathlib import Path as _Path
        _raw = sys.argv[1]
        # 이중 이스케이프 및 경로 정규화
        _txt_path = str(_Path(_raw).resolve())
        _file_name = _Path(_txt_path).name
        try:
            result = run_v8(fname=_txt_path, file_name=_file_name)
            print(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(0)

    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=TARGET_FILE)
    args = parser.parse_args()
    run_v8(args.file)