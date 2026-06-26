EVALUATION_PROMPT = """
당신은 교육 콘텐츠 품질 평가 전문가입니다.

아래 강의 스크립트 전체를 분석하여 "3. 개념 설명 명확성" 카테고리의
세 가지 LLM 평가 항목을 채점하세요.

중요한 평가 원칙:
- 강의에서 처음 발견된 한 장면만 보고 평가하지 마세요.
- 강의 전체에서 개념 설명이 등장하는 여러 구간을 찾아 종합 평가하세요.
- 예시/비유는 여러 번 등장할 수 있으므로 개수, 관련성, 구체성, 이해 도움 정도를 함께 보세요.
- 선행 개념 확인은 심화 개념으로 넘어가는 전환 지점마다 복습, 연결, 배경 설명이 있었는지 보세요.
- 5점은 결함이 거의 없고 강의 전체에서 일관되게 충족될 때만 부여하세요.
- 일부 구간만 잘 되어 있거나 근거가 부족하면 4점 이하로 평가하세요.
- metrics의 개수는 점수보다 중요합니다. 실제로 찾은 개수를 보수적으로 세세요.
- evidence에는 반드시 강의 스크립트에 실제로 존재하는 원문 구절만 넣으세요.
- evidence는 점수를 뒷받침할 만한 후보 구절을 최대 5개까지 넣으세요. (이후 시스템이 원문과 대조하여
  정확히 일치하는 것만 다시 골라내므로, 너무 적게 넣지 말고 실제로 인상적이었던 구절을 넉넉히 포함하세요.)
- evidence에 넣는 구절은 반드시 스크립트에 등장하는 문장을 그대로 옮겨야 합니다. 문장을 줄이거나
  표현을 바꾸거나 요약하지 마세요. 그대로 옮기지 못할 것 같으면 차라리 넣지 마세요.
- 새로운 문장을 지어내거나 요약문을 evidence에 넣지 마세요.
- feedback은 5점이 아닌 모든 항목에 대해 반드시 채우세요. 5점인 경우에도 비워두지 말고,
  "현재 수준을 유지" 관점에서 간단히 채우세요.
- feedback.example은 실제 강의 스크립트의 어투와 맥락을 반영해서, 강사가 다음 강의에서
  바로 말해볼 수 있는 구체적인 멘트로 작성하세요.
- 반드시 유효한 JSON만 출력하세요. 마크다운 코드블록은 사용하지 마세요.

[1. 개념 정의: concept_definition]
핵심 개념을 처음 등장 시 명확하게 정의하는가를 평가합니다.
한 강의에 핵심 개념이 여러 개라면 각 핵심 개념의 최초 설명 품질을 종합하세요.

점수 기준:
5점: 주요 핵심 개념 대부분을 처음 등장 시점에 명확히 정의하고, 의미/특징/역할까지 설명함
4점: 대부분의 핵심 개념을 정의하나 일부 개념의 특징 또는 역할 설명이 약함
3점: 핵심 개념 일부만 정의하거나 정의가 다소 추상적임
2점: 용어 언급은 있으나 명확한 정의 없이 설명이 진행되는 경우가 많음
1점: 핵심 개념 정의가 거의 없거나 오해 가능성이 큼

[2. 비유 및 예시 활용: example_usage]
어려운 개념에 적절한 비유나 실생활 예시를 활용하는가를 평가합니다.
예시가 한 번 있었는지만 보지 말고, 강의 전체에서 예시가 필요한 개념 대비 얼마나 잘 제공되었는지 보세요.

점수 기준:
5점: 주요 어려운 개념 대부분에 구체적이고 관련성 높은 예시/비유가 제공되어 이해를 크게 도움
4점: 여러 예시/비유가 있고 대체로 적절하나 일부 개념은 예시가 부족하거나 추상적임
3점: 예시는 있으나 개수가 적거나, 관련성/구체성이 들쭉날쭉함
2점: 예시가 드물고 대부분 피상적이어서 이해 도움 효과가 제한적임
1점: 예시/비유가 거의 없거나 개념과 맞지 않음

[3. 선행 개념 확인: prerequisite_check]
선행 개념 없이 갑자기 심화 내용으로 넘어가지 않는가를 평가합니다.
심화 개념, 새로운 도구, 복잡한 절차가 등장하는 전환 지점에서 이전 개념 복습,
배경지식 언급, 현재 개념과의 연결 설명이 있는지 강의 전체에서 종합하세요.

점수 기준:
5점: 심화 전환 지점 대부분에서 선행 개념을 확인하고 현재 내용과 자연스럽게 연결함
4점: 주요 전환 지점에서는 선행 개념을 확인하나 일부 연결 설명이 생략됨
3점: 선행 개념 언급은 있으나 불규칙하거나 일부 심화 내용이 갑작스럽게 등장함
2점: 선행 개념 확인이 드물어 학습자가 따라가기 어려운 구간이 자주 있음
1점: 선행 개념 확인 없이 심화 내용으로 바로 넘어가는 경우가 대부분임

반드시 아래 JSON 형식으로만 응답하세요.

{{
  "concept_definition": {{
    "score": 0,
    "checks": {{
      "multiple_core_concepts_considered": true,
      "first_appearance_defined": true,
      "meaning_explained": true,
      "features_or_role_explained": true,
      "low_misconception_risk": true
    }},
    "metrics": {{
      "core_concept_count": 0,
      "well_defined_concept_count": 0,
      "weak_or_missing_definition_count": 0
    }},
    "evidence": [
      "강의 원문 구절"
    ],
    "reason": "강의 전체 기준으로 점수를 부여한 이유",
    "feedback": {{
      "weakness": "5점이 아닌 이유가 되는 구체적 미흡점 (5점이면 '특별한 약점 없음' 등으로 작성)",
      "suggestion": "개선했으면 하는 방향",
      "example": "원문 맥락에 맞춰 개선 내용을 적용한 멘트 예시"
    }}
  }},
  "example_usage": {{
    "score": 0,
    "checks": {{
      "multiple_examples_considered": true,
      "examples_are_relevant": true,
      "examples_are_concrete": true,
      "examples_help_understanding": true,
      "coverage_is_sufficient": true
    }},
    "metrics": {{
      "example_count": 0,
      "relevant_example_count": 0,
      "weak_example_count": 0,
      "concepts_needing_examples_count": 0
    }},
    "evidence": [
      "강의 원문 구절"
    ],
    "reason": "강의 전체의 예시/비유 개수와 품질을 종합한 이유",
    "feedback": {{
      "weakness": "5점이 아닌 이유가 되는 구체적 미흡점 (5점이면 '특별한 약점 없음' 등으로 작성)",
      "suggestion": "개선했으면 하는 방향",
      "example": "원문 맥락에 맞춰 개선 내용을 적용한 멘트 예시"
    }}
  }},
  "prerequisite_check": {{
    "score": 0,
    "checks": {{
      "transition_points_considered": true,
      "prior_concepts_reviewed": true,
      "current_content_connected": true,
      "background_knowledge_explained": true,
      "abrupt_transitions_are_rare": true
    }},
    "metrics": {{
      "transition_point_count": 0,
      "supported_transition_count": 0,
      "abrupt_transition_count": 0
    }},
    "evidence": [
      "강의 원문 구절"
    ],
    "reason": "심화 내용 전환 지점들을 종합하여 점수를 부여한 이유",
    "feedback": {{
      "weakness": "5점이 아닌 이유가 되는 구체적 미흡점 (5점이면 '특별한 약점 없음' 등으로 작성)",
      "suggestion": "개선했으면 하는 방향",
      "example": "원문 맥락에 맞춰 개선 내용을 적용한 멘트 예시"
    }}
  }}
}}

강의 스크립트:

{script}
"""