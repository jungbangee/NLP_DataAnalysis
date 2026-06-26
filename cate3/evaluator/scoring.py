def clamp_score(value, min_score=0, max_score=5):
    try:
        score = int(value)
    except (TypeError, ValueError):
        return min_score

    return max(min_score, min(score, max_score))


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def score_ratio(success_count, total_count):
    if total_count <= 0:
        return 0

    ratio = min(success_count, total_count) / total_count

    if ratio >= 0.85:
        return 5
    if ratio >= 0.70:
        return 4
    if ratio >= 0.50:
        return 3
    if ratio >= 0.30:
        return 2
    return 1


def cap_by_checks(score, checks):
    if not checks:
        return score

    true_count = sum(1 for value in checks.values() if value is True)
    total_count = len(checks)

    if total_count == 0:
        return score

    check_ratio = true_count / total_count

    if check_ratio >= 0.90:
        cap = 5
    elif check_ratio >= 0.70:
        cap = 4
    elif check_ratio >= 0.50:
        cap = 3
    elif check_ratio >= 0.30:
        cap = 2
    else:
        cap = 1

    return min(score, cap)


def select_representative_evidence(evidence_list, max_items=3):
    valid_evidence = [
        item
        for item in evidence_list
        if item.get("match_type") in {"exact", "similar"}
    ]

    if valid_evidence:
        candidates = valid_evidence
    else:
        candidates = evidence_list

    return sorted(
        candidates,
        key=lambda item: item.get("similarity", 0),
        reverse=True
    )[:max_items]


def adjust_score_by_evidence(score, evidence_list):
    score = clamp_score(score)

    if not evidence_list:
        return min(score, 2)

    total_count = len(evidence_list)
    hallucination_count = sum(
        1
        for item in evidence_list
        if item.get("match_type") == "hallucination"
    )
    valid_count = total_count - hallucination_count

    if valid_count <= 0:
        return min(score, 1)

    hallucination_ratio = hallucination_count / total_count

    if hallucination_ratio >= 0.50:
        score -= 2
    elif hallucination_ratio >= 0.25:
        score -= 1

    if valid_count < 2 and score >= 4:
        score = 3

    return clamp_score(score, min_score=1)


def score_concept_definition(category):
    metrics = category.get("metrics", {})
    checks = category.get("checks", {})

    core_count = safe_int(metrics.get("core_concept_count"))
    well_defined_count = safe_int(metrics.get("well_defined_concept_count"))
    weak_count = safe_int(metrics.get("weak_or_missing_definition_count"))

    if core_count <= 0:
        score = clamp_score(category.get("score", 0), max_score=3)
    else:
        score = score_ratio(well_defined_count, core_count)

    if weak_count > 0 and score == 5:
        score = 4
    if weak_count >= core_count and core_count > 0:
        score = min(score, 2)

    return cap_by_checks(score, checks)


def score_example_usage(category):
    metrics = category.get("metrics", {})
    checks = category.get("checks", {})

    example_count = safe_int(metrics.get("example_count"))
    relevant_count = safe_int(metrics.get("relevant_example_count"))
    weak_count = safe_int(metrics.get("weak_example_count"))
    need_count = safe_int(metrics.get("concepts_needing_examples_count"))

    if example_count <= 0:
        score = 1
    elif need_count > 0:
        score = score_ratio(relevant_count, need_count)
    else:
        score = score_ratio(relevant_count, example_count)
        score = min(score, 4)

    if weak_count > 0 and score == 5:
        score = 4
    if weak_count >= relevant_count and weak_count > 0:
        score = min(score, 2)

    return cap_by_checks(score, checks)


def score_prerequisite_check(category):
    metrics = category.get("metrics", {})
    checks = category.get("checks", {})

    transition_count = safe_int(metrics.get("transition_point_count"))
    supported_count = safe_int(metrics.get("supported_transition_count"))
    abrupt_count = safe_int(metrics.get("abrupt_transition_count"))

    if transition_count <= 0:
        score = clamp_score(category.get("score", 0), max_score=3)
    else:
        score = score_ratio(supported_count, transition_count)

    if abrupt_count > 0 and score == 5:
        score = 4
    if abrupt_count >= supported_count and abrupt_count > 0:
        score = min(score, 2)

    return cap_by_checks(score, checks)


def calculate_gemini_score(result):
    return {
        "concept_definition": score_concept_definition(
            result["concept_definition"]
        ),
        "example_usage": score_example_usage(
            result["example_usage"]
        ),
        "prerequisite_check": score_prerequisite_check(
            result["prerequisite_check"]
        )
    }
