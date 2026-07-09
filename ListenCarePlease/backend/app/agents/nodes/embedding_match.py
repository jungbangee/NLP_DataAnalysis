"""
embedding_match_node
음성 + 텍스트 임베딩으로 자동 매칭 시도
"""
from app.agents.state import AgentState
from app.agents.tools.voice_similarity_tool import calculate_voice_similarity
from app.agents.tools.text_similarity_tool import calculate_text_similarity


def extract_speaker_texts(speaker_label: str, stt_result: list, diar_result: dict) -> list:
    """
    특정 화자의 발화 텍스트 추출
    """
    utterances = []
    for segment in stt_result:
        if segment.get("speaker") == speaker_label:
            utterances.append(segment.get("text", ""))
    return utterances


async def embedding_match_node(state: AgentState) -> AgentState:
    """
    음성 + 텍스트 임베딩으로 자동 매칭을 시도합니다.
    임계값(0.85) 이상이면 자동 매칭 성공.
    프로필이 없으면 스킵.
    """
    auto_matched = {}
    previous_profiles = state.get("previous_profiles", [])

    # 프로필이 없으면 스킵
    if not previous_profiles:
        state["auto_matched"] = auto_matched
        return state

    embeddings = state["diar_result"].get("embeddings", {})

    for speaker_label, voice_emb in embeddings.items():
        # 이 화자의 발화들 추출
        utterances = extract_speaker_texts(speaker_label, state["stt_result"], state["diar_result"])

        if not utterances:
            continue

        # Tool 1: 음성 유사도
        voice_result = await calculate_voice_similarity.ainvoke({
            "new_embedding": voice_emb,
            "stored_profiles": previous_profiles
        })

        # Tool 2: 텍스트 유사도
        text_result = await calculate_text_similarity.ainvoke({
            "current_utterances": utterances,
            "stored_profiles": previous_profiles
        })

        # 둘 다 임계값 통과 & 같은 사람 지목
        if (voice_result["threshold_passed"] and
            text_result["similarity"] > 0.85 and
            voice_result["matched_profile"] == text_result["matched_profile"] and
            voice_result["matched_profile"] is not None):

            auto_matched[speaker_label] = voice_result["matched_profile"]

    state["auto_matched"] = auto_matched
    return state

