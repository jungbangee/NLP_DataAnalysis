"""
name_extraction_node
DetectedName 데이터에서 name_mentions 구성 및 화자별 발화 그룹화
"""
from app.agents.state import AgentState
from collections import defaultdict


def group_by_speaker(stt_result: list) -> dict:
    """
    화자별로 발화 그룹화
    """
    speaker_utterances = defaultdict(list)
    
    for segment in stt_result:
        speaker = segment.get("speaker", "UNKNOWN")
        text = segment.get("text", "")
        if text:
            speaker_utterances[speaker].append(text)
    
    return dict(speaker_utterances)


async def name_extraction_node(state: AgentState) -> AgentState:
    """
    DetectedName 데이터 활용 (NER 결과)
    context_before/after는 이미 DB에 저장되어 있음
    """
    # name_mentions는 이미 load_agent_input_data에서 구성됨
    # state에 그대로 전달
    name_mentions = state.get("name_mentions", [])

    # 화자별 발화 그룹화
    speaker_utterances = group_by_speaker(state["stt_result"])

    state["name_mentions"] = name_mentions
    state["speaker_utterances"] = speaker_utterances

    return state

