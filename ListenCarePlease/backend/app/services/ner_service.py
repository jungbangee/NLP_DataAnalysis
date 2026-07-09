"""
NER (Named Entity Recognition) Service
이름 추출 및 군집화를 담당하는 서비스
닉네임 태깅도 함께 처리
"""
import logging
from typing import List, Dict, Optional, Set
import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform
import Levenshtein
from transformers import pipeline

logger = logging.getLogger(__name__)


class NERService:
    """
    한국어 개인정보(이름) 추출 및 군집화 서비스
    """

    def __init__(
        self,
        model_name: str = "seungkukim/korean-pii-masking",
        ner_threshold: float = 0.6,
        cluster_threshold: float = 1.5
    ):
        """
        Args:
            model_name: Hugging Face NER 모델 이름
            ner_threshold: NER 신뢰도 임계값 (0.0 ~ 1.0)
            cluster_threshold: 레벤슈타인 거리 기반 군집화 임계값
        """
        self.ner_threshold = ner_threshold
        self.cluster_threshold = cluster_threshold

        logger.info(f"NER 모델 로딩 중: {model_name}")
        # device=-1은 CPU 사용을 의미 (CUDA가 있으면 device=0 사용 가능)
        self.ner_pipeline = pipeline(
            "token-classification",
            model=model_name,
            aggregation_strategy="simple",
            device=-1  # CPU 사용
        )
        logger.info("✓ NER 모델 로드 완료")

    def extract_person_names(
        self,
        ner_results: List[Dict],
        threshold: Optional[float] = None
    ) -> List[Dict[str, float]]:
        """
        NER 결과에서 PERSON 엔티티 추출

        Args:
            ner_results: Transformers NER pipeline 결과
            threshold: 신뢰도 임계값 (None이면 self.ner_threshold 사용)

        Returns:
            List[{"name": str, "score": float}]
        """
        if not ner_results:
            return []

        threshold = threshold or self.ner_threshold
        persons = []

        for entity in ner_results:
            if entity['score'] >= threshold and entity['entity_group'] == 'PS_NAME':
                persons.append({
                    'name': entity['word'],
                    'score': entity['score']
                })

        return persons

    def cluster_names(
        self,
        name_score_dict: Dict[str, float],
        threshold: Optional[float] = None
    ) -> Dict[str, any]:
        """
        레벤슈타인 거리 기반 이름 군집화 (score 기반 대표명 선정)

        Args:
            name_score_dict: {"이름": 최대_score, ...}
            threshold: 군집화 거리 임계값 (None이면 self.cluster_threshold 사용)

        Returns:
            {
                "대표명1": ["유사명1", "유사명2"],
                "대표명2": ["대표명2"]
            }
        """
        if len(name_score_dict) == 0:
            return {}

        threshold = threshold or self.cluster_threshold
        names = list(name_score_dict.keys())

        if len(names) == 1:
            return {names[0]: [names[0]]}

        n = len(names)
        distance_matrix = np.zeros((n, n))

        # 레벤슈타인 거리 계산
        for i in range(n):
            for j in range(i+1, n):
                dist = Levenshtein.distance(names[i], names[j])
                distance_matrix[i][j] = dist
                distance_matrix[j][i] = dist

        # 계층적 군집화
        condensed_dist = squareform(distance_matrix)
        linkage_matrix = linkage(condensed_dist, method='average')
        clusters = fcluster(linkage_matrix, threshold, criterion='distance')

        # 군집별로 그룹화
        cluster_dict = {}
        for name, cluster_id in zip(names, clusters):
            if cluster_id not in cluster_dict:
                cluster_dict[cluster_id] = []
            cluster_dict[cluster_id].append(name)

        # 대표명 선정 (score 기준)
        name_clusters = {}
        for cluster_id, cluster_names in cluster_dict.items():
            # score 기준으로 정렬하여 가장 높은 score를 가진 이름을 대표명으로 선정
            cluster_names_sorted = sorted(
                cluster_names,
                key=lambda x: name_score_dict[x],
                reverse=True
            )
            representative = cluster_names_sorted[0]
            name_clusters[representative] = cluster_names_sorted

        return name_clusters

    def process_segments(
        self,
        segments: List[Dict]
    ) -> Dict:
        """
        STT 세그먼트에서 이름 추출 및 군집화 수행
        닉네임 태깅도 함께 처리

        Args:
            segments: [{"text": str, "start": float, "end": float, "speaker": str}, ...]

        Returns:
            {
                "segments_with_names": [...],  # 각 세그먼트에 name 필드 추가
                "name_clusters": {...},         # 군집화된 이름들
                "final_namelist": [...],        # 최종 대표명 목록
                "unique_names": [...],          # 중복 제거된 모든 이름
                "name_found_count": int,        # 이름이 발견된 세그먼트 수
                "nicknames": {...},             # 화자별 닉네임 {speaker_label: {nickname, nickname_metadata}}
                "stats": {...}                  # 통계 정보
            }
        """
        logger.info(f"NER 처리 시작: {len(segments)}개 세그먼트")

        segments_with_names = []
        all_names = []
        name_scores = {}  # 이름별 최대 score 저장

        # 각 세그먼트에서 이름 추출
        for idx, segment in enumerate(segments):
            if (idx + 1) % 100 == 0:
                logger.info(f"  진행: {idx + 1}/{len(segments)}")

            text = segment.get('text', '')
            start_time = segment.get('start')
            end_time = segment.get('end')
            speaker = segment.get('speaker')

            # NER 수행
            ner_results = self.ner_pipeline(text)
            person_names_with_scores = self.extract_person_names(ner_results)

            # 이름만 추출
            person_names = [item['name'] for item in person_names_with_scores]

            # 각 이름의 최대 score 업데이트
            for item in person_names_with_scores:
                name = item['name']
                score = float(item['score'])  # numpy float32 -> Python float 변환
                if name not in name_scores or score > name_scores[name]:
                    name_scores[name] = score

            # 세그먼트에 이름 정보 추가
            segment_with_name = {
                'text': text,
                'start': start_time,
                'end': end_time,
                'speaker': speaker,
                'name': person_names if person_names else None,
                'has_name': len(person_names) > 0
            }

            segments_with_names.append(segment_with_name)

            if person_names:
                all_names.extend(person_names)

        # 고유 이름 추출
        unique_names = sorted(set(all_names))
        logger.info(f"✓ NER 완료: {len(unique_names)}개 고유 이름 추출")

        # 이름 군집화
        if len(unique_names) > 0:
            logger.info(f"이름 군집화 시작 (임계값: {self.cluster_threshold})")
            name_clusters = self.cluster_names(name_scores)
            final_namelist = sorted(name_clusters.keys())

            multi_clusters = sum(
                1 for v in name_clusters.values()
                if isinstance(v, list) and len(v) > 1
            )
            logger.info(
                f"✓ 군집화 완료: {len(unique_names)} → {len(final_namelist)}개 대표명 "
                f"(유사 이름 군집: {multi_clusters}개)"
            )
        else:
            name_clusters = {}
            final_namelist = []
            logger.info("추출된 이름 없음")

        # 닉네임 태깅 처리 (이름과 함께 처리)
        logger.info("닉네임 태깅 시작...")
        nickname_result = {}
        try:
            from app.services.nickname_service import get_nickname_service
            nickname_service = get_nickname_service()
            nickname_result = nickname_service.process_speakers_for_nicknames(segments)
            logger.info(f"✓ 닉네임 태깅 완료: {len(nickname_result)}개 화자")
        except Exception as nickname_error:
            logger.warning(f"⚠️ 닉네임 태깅 실패 (계속 진행): {nickname_error}")
            nickname_result = {}

        # 통계 계산
        name_found_count = sum(1 for seg in segments_with_names if seg['has_name'])

        result = {
            "segments_with_names": segments_with_names,
            "name_clusters": name_clusters,
            "final_namelist": final_namelist,
            "unique_names": unique_names,
            "name_found_count": name_found_count,
            "nicknames": nickname_result,  # 닉네임 결과 추가
            "stats": {
                "total_segments": len(segments),
                "segments_with_names": name_found_count,
                "percentage": (name_found_count / len(segments) * 100) if segments else 0,
                "unique_names_count": len(unique_names),
                "representative_names_count": len(final_namelist),
                "name_scores": name_scores
            }
        }

        logger.info(
            f"✓ NER 처리 완료: "
            f"{name_found_count}/{len(segments)}개 세그먼트에서 이름 발견 "
            f"({result['stats']['percentage']:.1f}%), "
            f"닉네임 {len(nickname_result)}개"
        )

        return result

    def generate_name_check_transcript(
        self,
        segments_with_names: List[Dict],
        unique_names: Set[str]
    ) -> List[str]:
        """
        이름 체크 트랜스크립트 생성 (프론트엔드 표시용)

        Args:
            segments_with_names: NER 결과가 포함된 세그먼트들
            unique_names: 고유 이름 집합

        Returns:
            ["[v] '민서씨, 오늘 회의 시작하겠습니다'", "[ ] '네, 알겠습니다'", ...]
        """
        unique_names_set = set(unique_names)
        output_lines = []

        for segment in segments_with_names:
            text = segment['text']
            names = segment.get('name')

            # unique_names에 있는 이름이 하나라도 포함되어 있는지 확인
            has_valid_name = False
            if names is not None and names != [] and names != '':
                # names가 리스트인 경우
                if isinstance(names, list):
                    for name in names:
                        if name in unique_names_set:
                            has_valid_name = True
                            break
                # names가 문자열인 경우
                elif isinstance(names, str):
                    if names in unique_names_set:
                        has_valid_name = True

            check_mark = 'v' if has_valid_name else ' '
            line = f"[{check_mark}] '{text}'"
            output_lines.append(line)

        return output_lines


# 싱글톤 인스턴스
_ner_service_instance: Optional[NERService] = None


def get_ner_service() -> NERService:
    """
    NER 서비스 싱글톤 인스턴스 반환
    """
    global _ner_service_instance

    if _ner_service_instance is None:
        _ner_service_instance = NERService()

    return _ner_service_instance
