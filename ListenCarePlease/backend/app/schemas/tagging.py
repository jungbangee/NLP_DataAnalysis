from pydantic import BaseModel
from typing import List, Optional


class DetectedNameItem(BaseModel):
    """감지된 이름 항목"""
    name: str
    confidence: float


class SuggestedMapping(BaseModel):
    """화자 매핑 제안"""
    speaker_label: str  # SPEAKER_00, SPEAKER_01, ...
    suggested_name: Optional[str] = None  # 시스템 제안 이름
    nickname: Optional[str] = None  # LLM이 생성한 닉네임 (예: "진행 담당자", "기술 전문가")
    final_name: Optional[str] = None  # 사용자가 확정한 이름


class TaggingSuggestionResponse(BaseModel):
    """화자 태깅 제안 응답 (I,O.md Step 5d)"""
    file_id: str
    detected_names: List[str]  # 감지된 모든 이름 리스트
    suggested_mappings: List[SuggestedMapping]  # 각 화자에 대한 제안


class TranscriptSegment(BaseModel):
    """대본 세그먼트 (참고용)"""
    speaker_label: str
    start_time: float
    end_time: float
    text: str


class TaggingSuggestionDetailResponse(BaseModel):
    """태깅 제안 상세 응답 (참고용 대본 포함)"""
    file_id: str
    detected_names: List[str]
    detected_nicknames: Optional[List[str]] = None  # 감지된 닉네임 리스트
    suggested_mappings: List[SuggestedMapping]
    sample_transcript: List[TranscriptSegment]  # 참고용 대본 샘플


class SpeakerMappingConfirm(BaseModel):
    """사용자 확정 요청 (I,O.md Step 5e)"""
    speaker_label: str
    final_name: str


class TaggingConfirmRequest(BaseModel):
    """화자 태깅 확정 요청"""
    file_id: str
    mappings: List[SpeakerMappingConfirm]


class TaggingConfirmResponse(BaseModel):
    """화자 태깅 확정 응답"""
    file_id: str
    message: str
    status: str


class SpeakerInfoConfirmRequest(BaseModel):
    """화자 정보 확정 요청"""
    file_id: str
    speaker_count: int
    detected_names: List[str]
    detected_nicknames: Optional[List[str]] = None  # 선택된 닉네임 리스트
