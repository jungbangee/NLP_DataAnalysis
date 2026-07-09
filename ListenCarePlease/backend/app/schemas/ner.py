"""
NER (Named Entity Recognition) Schemas
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional


class PersonName(BaseModel):
    """개별 이름 정보"""
    name: str = Field(..., description="추출된 이름")
    score: float = Field(..., ge=0.0, le=1.0, description="NER 신뢰도 점수")


class SegmentWithName(BaseModel):
    """이름 정보가 포함된 세그먼트"""
    text: str = Field(..., description="발화 텍스트")
    start: Optional[float] = Field(None, description="시작 시간 (초)")
    end: Optional[float] = Field(None, description="종료 시간 (초)")
    speaker: Optional[str] = Field(None, description="화자 라벨 (SPEAKER_00, ...)")
    name: Optional[List[str]] = Field(None, description="추출된 이름 목록")
    has_name: bool = Field(default=False, description="이름 포함 여부")


class NERStats(BaseModel):
    """NER 처리 통계"""
    total_segments: int = Field(..., description="전체 세그먼트 수")
    segments_with_names: int = Field(..., description="이름이 발견된 세그먼트 수")
    percentage: float = Field(..., description="이름 발견 비율 (%)")
    unique_names_count: int = Field(..., description="고유 이름 수")
    representative_names_count: int = Field(..., description="대표명 수 (군집화 후)")
    name_scores: Dict[str, float] = Field(default_factory=dict, description="이름별 최대 신뢰도 점수")


class NERResult(BaseModel):
    """NER 처리 결과"""
    segments_with_names: List[SegmentWithName] = Field(..., description="이름 정보가 추가된 세그먼트들")
    name_clusters: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="군집화된 이름들 (대표명: [유사명들])"
    )
    final_namelist: List[str] = Field(default_factory=list, description="최종 대표명 목록")
    unique_names: List[str] = Field(default_factory=list, description="중복 제거된 모든 이름")
    name_found_count: int = Field(..., description="이름이 발견된 세그먼트 수")
    stats: NERStats = Field(..., description="통계 정보")


class NERRequest(BaseModel):
    """NER 요청 스키마"""
    segments: List[Dict] = Field(..., description="STT 세그먼트 목록")
    ner_threshold: Optional[float] = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="NER 신뢰도 임계값"
    )
    cluster_threshold: Optional[float] = Field(
        default=1.5,
        ge=0.0,
        description="군집화 거리 임계값"
    )


class NERResponse(BaseModel):
    """NER 응답 스키마"""
    success: bool = Field(..., description="처리 성공 여부")
    message: str = Field(..., description="처리 결과 메시지")
    result: Optional[NERResult] = Field(None, description="NER 처리 결과")
    error: Optional[str] = Field(None, description="에러 메시지")
