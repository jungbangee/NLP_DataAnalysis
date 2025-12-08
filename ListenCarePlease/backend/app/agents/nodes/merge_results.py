"""
최종 화자 매핑 통합 노드

- name_based_results 스코어 집계
- 중복 이름 제거 (같은 이름이 여러 화자에 매핑된 경우 최고 스코어 선택)
- 소거법 적용 (1:1 매칭 시 자동 매핑)
- 신뢰도 기반 수동 검토 필요 여부 판단
"""
from typing import Dict, Set, List
from collections import defaultdict
from app.agents.state import AgentState


def find_matching_name(speaker_label: str, name_based_results: dict) -> Dict:
    """특정 화자에 매핑된 이름 찾기"""
    for name, results in name_based_results.items():
        for result in results:
            if result.get("speaker") == speaker_label:
                return result
    return None


def apply_elimination_method(
    mapping: Dict[str, Dict],
    all_speakers: Set[str],
    participant_names: List[str],
    speaker_utterances: Dict[str, List[str]]
) -> Dict[str, Dict]:
    """
    소거법 적용
    1. 중복 이름 제거: 같은 이름이 여러 화자에 매핑된 경우 최고 스코어 선택
    2. 1:1 매칭: 남은 화자 수 == 남은 이름 수일 때 자동 매핑 (최소 3회 발화 필요)
    """
    refined_mapping = {}

    # 1. 중복 이름 제거
    name_to_speakers = defaultdict(list)
    for speaker, info in mapping.items():
        name = info.get("name")
        if name:
            name_to_speakers[name].append((speaker, info))

    removed_speakers = []
    for name, speakers_list in name_to_speakers.items():
        if len(speakers_list) > 1:
            # confidence와 evidence_count 기준으로 최고 스코어 선택
            best_speaker, best_info = max(
                speakers_list,
                key=lambda x: (x[1].get("confidence", 0), x[1].get("evidence_count", 0))
            )
            refined_mapping[best_speaker] = best_info
            for spk, _ in speakers_list:
                if spk != best_speaker:
                    removed_speakers.append(spk)
        else:
            refined_mapping[speakers_list[0][0]] = speakers_list[0][1]

    # 2. 소거법 적용
    mapped_speakers = set(refined_mapping.keys())
    unmapped_speakers = all_speakers - mapped_speakers

    used_names = {info.get("name") for info in refined_mapping.values() if info.get("name")}
    unused_names = set(participant_names) - used_names

    # 소거법 적용 (남은 화자 수 == 남은 이름 수)
    if len(unmapped_speakers) == len(unused_names) and len(unmapped_speakers) > 0:
        for speaker in sorted(unmapped_speakers):
            utterances = speaker_utterances.get(speaker, [])
            utterance_count = len(utterances)

            if utterance_count >= 3:
                if unused_names:
                    remaining_name = list(unused_names)[0]
                    refined_mapping[speaker] = {
                        "name": remaining_name,
                        "confidence": 0.50,
                        "method": "소거법",
                        "evidence_count": 0,
                        "utterance_count": utterance_count
                    }
                    unused_names.remove(remaining_name)

    return refined_mapping


async def merge_results_node(state: AgentState) -> AgentState:
    """
    최종 화자 매핑 생성
    - auto_matched (임베딩 매칭) 결과 우선 사용
    - name_based_results 스코어 집계 및 중복 제거
    - 소거법 적용
    - 신뢰도 0.7 미만 또는 소거법 매핑 시 수동 검토 필요
    """
    final_mappings = {}
    needs_review = []

    # 자동 매칭된 화자는 그대로 사용
    for speaker_label, name in state.get("auto_matched", {}).items():
        final_mappings[speaker_label] = {
            "speaker_label": speaker_label,
            "name": name,
            "match_method": "embedding",
            "auto_matched": True,
            "confidence": 1.0,  # 자동 매칭은 높은 신뢰도
            "needs_review": False
        }

    name_based_results = state.get("name_based_results", {})
    speaker_utterances = state.get("speaker_utterances", {})
    participant_names = state.get("participant_names", [])

    all_speakers = set(speaker_utterances.keys())

    speaker_name_scores = defaultdict(lambda: {"names": [], "confidences": [], "evidence_count": 0})

    for name, results in name_based_results.items():
        for result in results:
            speaker = result.get("speaker")
            if speaker and speaker != "Unknown":
                speaker_name_scores[speaker]["names"].append(result.get("name"))
                speaker_name_scores[speaker]["confidences"].append(result.get("confidence", 0.0))
                speaker_name_scores[speaker]["evidence_count"] += 1

    initial_mapping = {}
    for speaker_label in all_speakers:
        if speaker_label in state.get("auto_matched", {}):
            continue

        scores = speaker_name_scores.get(speaker_label, {"names": [], "confidences": [], "evidence_count": 0})
        if scores.get("names"):
            name_counts = defaultdict(lambda: {"count": 0, "total_confidence": 0.0})
            for name, conf in zip(scores["names"], scores["confidences"]):
                name_counts[name]["count"] += 1
                name_counts[name]["total_confidence"] += conf

            best_name = max(
                name_counts.items(),
                key=lambda x: (x[1]["count"], x[1]["total_confidence"] / x[1]["count"])
            )[0]

            avg_confidence = name_counts[best_name]["total_confidence"] / name_counts[best_name]["count"]

            initial_mapping[speaker_label] = {
                "name": best_name,
                "confidence": avg_confidence,
                "evidence_count": scores["evidence_count"]
            }

    # 소거법 적용
    refined_mapping = apply_elimination_method(
        initial_mapping,
        all_speakers,
        participant_names,
        speaker_utterances
    )

    for speaker_label, info in refined_mapping.items():
        confidence = info.get("confidence", 0.0)
        method = info.get("method", "name_based")

        final_mappings[speaker_label] = {
            "speaker_label": speaker_label,
            "name": info.get("name", "Unknown"),
            "confidence": confidence,
            "match_method": method,
            "auto_matched": False,
            "needs_review": confidence < 0.7 or method == "소거법"
        }

        if final_mappings[speaker_label]["needs_review"]:
            needs_review.append(speaker_label)

    # 매핑되지 않은 화자 처리
    unmapped_speakers = [s for s in all_speakers if s not in final_mappings]
    used_names = {info.get("name") for info in final_mappings.values() if info.get("name") and info.get("name") != "Unknown"}
    unused_names = [n for n in participant_names if n not in used_names]

    if unmapped_speakers and unused_names:
        unmapped_scores = []
        for speaker_label in unmapped_speakers:
            scores = speaker_name_scores.get(speaker_label, {"names": [], "confidences": [], "evidence_count": 0})
            if scores.get("names"):
                name_scores = defaultdict(lambda: {"count": 0, "total_confidence": 0.0})
                for name, conf in zip(scores["names"], scores["confidences"]):
                    if name in unused_names:
                        name_scores[name]["count"] += 1
                        name_scores[name]["total_confidence"] += conf
                if name_scores:
                    best_name = max(
                        name_scores.items(),
                        key=lambda x: (x[1]["count"], x[1]["total_confidence"] / x[1]["count"])
                    )[0]
                    avg_confidence = name_scores[best_name]["total_confidence"] / name_scores[best_name]["count"]
                    score = (name_scores[best_name]["count"] * 0.5) + (avg_confidence * 0.5)
                    
                    unmapped_scores.append({
                        "speaker": speaker_label,
                        "name": best_name,
                        "confidence": avg_confidence,
                        "score": score,
                        "evidence_count": name_scores[best_name]["count"]
                    })
        unmapped_scores.sort(key=lambda x: x["score"], reverse=True)
        used_in_round = set()
        for item in unmapped_scores:
            if item["name"] not in used_in_round and item["name"] in unused_names:
                final_mappings[item["speaker"]] = {
                    "speaker_label": item["speaker"],
                    "name": item["name"],
                    "confidence": item["confidence"],
                    "match_method": "score_based",
                    "auto_matched": False,
                    "needs_review": item["confidence"] < 0.7
                }
                used_in_round.add(item["name"])
                unused_names.remove(item["name"])
                if final_mappings[item["speaker"]]["needs_review"]:
                    needs_review.append(item["speaker"])
        remaining_unmapped = [s for s in unmapped_speakers if s not in final_mappings]
        remaining_with_utterances = []
        for speaker_label in remaining_unmapped:
            utterances = speaker_utterances.get(speaker_label, [])
            utterance_count = len(utterances)
            if utterance_count >= 3:
                remaining_with_utterances.append((speaker_label, utterance_count))
        remaining_with_utterances.sort(key=lambda x: x[1], reverse=True)
        for speaker_label, utterance_count in remaining_with_utterances:
            if unused_names:
                remaining_name = unused_names[0]
                final_mappings[speaker_label] = {
                    "speaker_label": speaker_label,
                    "name": remaining_name,
                    "confidence": 0.50,
                    "match_method": "소거법",
                    "auto_matched": False,
                    "needs_review": True,
                    "utterance_count": utterance_count
                }
                unused_names.remove(remaining_name)
                needs_review.append(speaker_label)
    for speaker_label in all_speakers:
        if speaker_label not in final_mappings:
            final_mappings[speaker_label] = {
                "speaker_label": speaker_label,
                "name": "Unknown",
                "confidence": 0.0,
                "match_method": "none",
                "auto_matched": False,
                "needs_review": True
            }
            needs_review.append(speaker_label)

    state["final_mappings"] = final_mappings
    state["needs_manual_review"] = needs_review

    return state

