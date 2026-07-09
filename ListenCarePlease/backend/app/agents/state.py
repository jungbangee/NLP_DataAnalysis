"""
Agent State 정의
"""
from typing import TypedDict, List, Dict


class AgentState(TypedDict):
    """Agent State 정의"""
    # 입력 데이터
    user_id: int
    audio_file_id: int
    stt_result: List[Dict]           # [{text, start, end, speaker, has_name}, ...]
    diar_result: Dict                # {embeddings: {...}, turns: [...]}
    participant_names: List[str]     # 참여자 이름 목록

    # Agent가 생성하는 중간 데이터
    previous_profiles: List[Dict]    # DB에서 로드한 기존 화자 프로필
    auto_matched: Dict[str, str]     # 임베딩 자동 매칭 성공한 화자 {"SPEAKER_00": "김민서"}
    name_mentions: List[Dict]        # has_name=true인 것들 추출
    speaker_utterances: Dict         # 화자별로 묶은 발화들
    mapping_history: List[Dict]     # 멀티턴 추론 히스토리

    # LLM 판단 결과
    name_based_results: Dict         # 방식1 결과

    # 최종 출력
    final_mappings: Dict             # 통합된 최종 매핑
    needs_manual_review: List[str]   # 수동 확인 필요한 화자 목록
















