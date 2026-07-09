"""
이름 기반 태깅 프롬프트 템플릿
"""
from typing import List, Dict


def format_context_for_llm(
    context_before: List[Dict], 
    context_after: List[Dict], 
    target_name: str,
    target_text: str = None,
    target_speaker: str = None
) -> str:
    """
    LLM이 읽기 쉬운 형식으로 context 포맷 (대화흐름.ipynb와 동일하게)
    
    context_before/after는 DetectedName의 JSON 필드에서 가져온 것
    형식: [{"speaker": "SPEAKER_00", "text": "...", "start": 0.5, "end": 3.2}, ...]
    target_text: 실제 이름이 언급된 문장 (대화흐름.ipynb의 target['text'])
    target_speaker: target 문장의 화자
    """
    lines = []
    
    # context_before (이름 언급 전)
    if context_before:
        for seg in context_before:
            if isinstance(seg, dict):
                speaker = seg.get("speaker", "UNKNOWN")
                text = seg.get("text", "")
            else:
                # 문자열인 경우
                speaker = "UNKNOWN"
                text = str(seg)
            if text:
                lines.append(f"  [{speaker}] {text}")
    
    # 타겟 (이름 언급 지점) - 대화흐름.ipynb처럼 실제 문장 표시
    if target_text and target_speaker:
        lines.append(f"→ [{target_speaker}] {target_text}")
    else:
        lines.append(f"→ [이름 언급: '{target_name}']")
    
    # context_after (이름 언급 후)
    if context_after:
        for seg in context_after:
            if isinstance(seg, dict):
                speaker = seg.get("speaker", "UNKNOWN")
                text = seg.get("text", "")
            else:
                # 문자열인 경우
                speaker = "UNKNOWN"
                text = str(seg)
            if text:
                lines.append(f"  [{speaker}] {text}")
    
    return "\n".join(lines) if lines else "[맥락 없음]"


def get_history_summary(mapping_history: List[Dict], recent_count: int = 15) -> str:
    """
    이전 분석 결과 요약 생성
    - 각 이름에 대한 모든 스코어 표시
    - 최근 대화 맥락 포함
    """
    if not mapping_history:
        return ""
    
    # 최근 결과를 더 많이 가져오기 (최근 15개)
    recent = mapping_history[-recent_count:] if len(mapping_history) > recent_count else mapping_history
    
    # 이름별로 모든 분석 결과 수집 (스코어 포함)
    name_to_results = {}
    for h in recent:
        name_mentioned = h.get('name_mentioned', '')
        speaker = h.get('speaker', 'Unknown')
        name = h.get('name', 'Unknown')
        confidence = h.get('confidence', 0.0)
        turn = h.get('turn', 0)
        
        if name_mentioned and name != 'Unknown' and speaker != 'Unknown':
            if name_mentioned not in name_to_results:
                name_to_results[name_mentioned] = []
            name_to_results[name_mentioned].append({
                'speaker': speaker,
                'name': name,
                'confidence': confidence,
                'turn': turn
            })
    
    if not name_to_results:
        return ""
    
    # 이름별로 정리하여 표시
    summary = "이전 분석 결과 (각 이름별 모든 스코어):\n"
    for name_mentioned, results in sorted(name_to_results.items()):
        summary += f"\n'{name_mentioned}' 이름 분석 결과:\n"
        # 화자별로 그룹화
        speaker_to_scores = {}
        for r in results:
            speaker = r['speaker']
            if speaker not in speaker_to_scores:
                speaker_to_scores[speaker] = []
            speaker_to_scores[speaker].append({
                'name': r['name'],
                'confidence': r['confidence'],
                'turn': r['turn']
            })
        
        # 각 화자별로 모든 스코어 표시
        for speaker, scores_list in sorted(speaker_to_scores.items()):
            # 스코어를 신뢰도 순으로 정렬
            scores_list.sort(key=lambda x: x['confidence'], reverse=True)
            for score_info in scores_list:
                summary += f"  - {speaker} → {score_info['name']} (신뢰도: {score_info['confidence']:.2f}, 분석#{score_info['turn']})\n"
    
    return summary


def get_recent_conversation_context(mapping_history: List[Dict], recent_count: int = 5) -> str:
    """
    최근 대화 맥락 추출 (이전 분석에서 본 대화 내용)
    """
    if not mapping_history:
        return ""
    
    # 최근 분석 결과에서 대화 맥락 정보 추출
    recent = mapping_history[-recent_count:] if len(mapping_history) > recent_count else mapping_history
    
    context_lines = []
    for h in recent:
        turn = h.get('turn', 0)
        name_mentioned = h.get('name_mentioned', '')
        reasoning = h.get('reasoning', '')
        
        if name_mentioned and reasoning:
            context_lines.append(f"  [분석#{turn}] '{name_mentioned}' 분석: {reasoning[:100]}...")
    
    if not context_lines:
        return ""
    
    return "최근 대화 맥락:\n" + "\n".join(context_lines) + "\n"


def create_name_based_prompt(
    name: str,
    context_before: List[Dict],
    context_after: List[Dict],
    participant_names: List[str],
    mapping_history: List[Dict],
    turn_num: int,
    format_instructions: str,
    target_text: str = None,
    target_speaker: str = None
) -> tuple[str, str]:
    """
    이름 기반 태깅 프롬프트 생성 (대화흐름.ipynb와 동일하게)
    
    Returns:
        (system_message, user_message)
    """
    context_str = format_context_for_llm(
        context_before, 
        context_after, 
        name,
        target_text=target_text,
        target_speaker=target_speaker
    )
    history_summary = get_history_summary(mapping_history)
    recent_context = get_recent_conversation_context(mapping_history)
    
    system_message = f"""당신은 회의 전사본 화자 매핑 전문가입니다.

참여자 이름 목록: {', '.join(participant_names) if participant_names else '(없음)'}
⚠️ 중요: 위 목록에 있는 이름 중에서만 선택해야 합니다. 목록에 없는 이름은 선택할 수 없습니다.

분석 단서:
- 호칭 후 즉시 응답
- 3인칭 언급 후 반응
- 자기 지칭

이전 분석 결과를 기억하고 일관성을 확인하세요.

{format_instructions}"""

    user_message = f"""{history_summary}

{recent_context}

[분석 {turn_num}]

{context_str}

위 맥락에서 언급된 이름의 화자를 분석하세요. 이전 분석 결과와 최근 대화 맥락을 참고하여 일관성 있게 판단하세요."""

    return system_message, user_message

