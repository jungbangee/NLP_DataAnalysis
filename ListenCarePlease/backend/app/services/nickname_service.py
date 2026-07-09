"""
닉네임 태깅 서비스
LLM 기반으로 화자별 닉네임(역할/특징) 생성
"""
import logging
import json
import hashlib
import time
import re
from typing import List, Dict, Optional, Any
from pathlib import Path
from openai import OpenAI
from app.core.config import settings
from langsmith import traceable

logger = logging.getLogger(__name__)

# Smart Selection Parameters
MAX_UTTERANCES = 12  # 화자당 최대 발화 수
MIN_UTTERANCES = 3   # 최소 발화 수 (이하는 스킵)
TOP_LONG = 5         # 긴 발화 선택 수
TOP_KEYWORD = 3      # 키워드 발화 선택 수
TOP_TEMPORAL = 3     # 시점별 발화 선택 수

# Cost Management
MAX_COST_PER_MEETING = 10000  # 원화 기준
COST_INPUT_PER_1K = 0.00015    # USD per 1K input tokens
COST_OUTPUT_PER_1K = 0.0006    # USD per 1K output tokens
USD_TO_KRW = 1400

# Rate Limiting
MAX_CONCURRENT_REQUESTS = 5
DELAY_BETWEEN_BATCHES = 0.2
RETRY_MAX_ATTEMPTS = 2
RETRY_BACKOFF_BASE = 2

# Keywords for Smart Selection
IMPORTANT_KEYWORDS = ["요약", "정리", "결론", "제안", "문제", "해결",
                      "반대", "동의", "질문", "부탁", "요청", "확인"]

# LLM 프롬프트 템플릿
PROMPT_TEMPLATE = """당신은 전문 회의 분석가입니다.
아래 제공된 화자의 발화 내용을 분석하여 정확하고 통찰력 있는 프로파일을 생성해주세요.

[화자 정보]
- 화자 ID: {speaker_id}
- 총 발화 수: {total_utterances}
- 분석 대상 발화 수: {selected_utterances}

[대표 발화 내용]
{utterances_text}

[분석 요청사항]
위 발화 내용을 바탕으로 다음 항목들을 분석하여 JSON 형식으로 응답해주세요:

1. display_label: 이 사람의 회의에서의 역할이나 특징을 2-4단어로 표현
   예) "진행 담당자", "기술 전문가", "의견 조율자"
   ⚠️ 중요: 실명, 회사명, 팀명 등 고유명사는 절대 사용하지 마세요. 역할과 기능 중심으로만 표현하세요.

2. one_liner: 이 사람의 발화 스타일과 내용을 한 문장으로 요약

3. keywords: 이 사람의 발화에서 중요한 키워드 3-5개

4. communication_style: 의사소통 스타일 특징 2-3개
   예) ["질문형", "설명 위주", "간결함"]

5. stance_markers: 주요 입장이나 관점을 나타내는 표현 2-3개

6. evidence_utter_idx: 이 사람의 특징을 가장 잘 보여주는 발화 인덱스 3개

[JSON 응답 형식]
{{
  "display_label": "string (2-4 words)",
  "one_liner": "string (1 sentence)",
  "keywords": ["keyword1", "keyword2", "keyword3"],
  "communication_style": ["style1", "style2"],
  "stance_markers": ["marker1", "marker2"],
  "evidence_utter_idx": [idx1, idx2, idx3]
}}

[제약사항]
- 실명, 회사명, 팀명 등 고유명사는 절대 사용하지 마세요
- 역할과 기능 중심으로 표현하세요
- 모든 필드는 반드시 채워주세요
- evidence_utter_idx는 제공된 발화의 인덱스만 사용하세요"""


class NicknameService:
    """닉네임 태깅 서비스"""

    def __init__(self):
        """서비스 초기화"""
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        logger.info("✓ NicknameService 초기화 완료")

    def smart_selection(
        self,
        utterances: List[Dict],
        max_total: int = MAX_UTTERANCES
    ) -> List[Dict]:
        """
        Smart Selection: 긴 발화 + 키워드 + 시점별 균형 선택
        
        Args:
            utterances: [{"idx": int, "text": str, "start": float, "end": float}, ...]
            max_total: 최대 선택할 발화 수
            
        Returns:
            선택된 발화 리스트
        """
        if len(utterances) <= max_total:
            return utterances

        selected = []
        selected_indices = set()

        # 1. Top N 긴 발화
        longest = sorted(utterances, key=lambda x: len(x['text']), reverse=True)
        for utt in longest[:TOP_LONG]:
            if utt['idx'] not in selected_indices:
                selected.append(utt)
                selected_indices.add(utt['idx'])

        # 2. 키워드 포함 발화
        keyword_utts = []
        for utt in utterances:
            if utt['idx'] in selected_indices:
                continue
            keyword_score = sum(1 for kw in IMPORTANT_KEYWORDS if kw in utt['text'])
            if keyword_score > 0:
                keyword_utts.append((keyword_score, utt))

        keyword_utts.sort(key=lambda x: -x[0])
        for _, utt in keyword_utts[:TOP_KEYWORD]:
            if utt['idx'] not in selected_indices:
                selected.append(utt)
                selected_indices.add(utt['idx'])

        # 3. 시점별 분산 (초/중/후반)
        if len(utterances) >= 3:
            segment_size = len(utterances) // 3

            # 초반부
            early = utterances[:segment_size]
            if early:
                mid_idx = len(early) // 2
                if early[mid_idx]['idx'] not in selected_indices:
                    selected.append(early[mid_idx])
                    selected_indices.add(early[mid_idx]['idx'])

            # 중반부
            middle = utterances[segment_size:2*segment_size]
            if middle:
                mid_idx = len(middle) // 2
                if middle[mid_idx]['idx'] not in selected_indices:
                    selected.append(middle[mid_idx])
                    selected_indices.add(middle[mid_idx]['idx'])

            # 후반부
            late = utterances[2*segment_size:]
            if late:
                mid_idx = len(late) // 2
                if late[mid_idx]['idx'] not in selected_indices:
                    selected.append(late[mid_idx])
                    selected_indices.add(late[mid_idx]['idx'])

        # 4. 중복 제거 (텍스트 해시 기반)
        seen_hashes = set()
        unique_selected = []
        for utt in selected:
            text_hash = hash(utt['text'][:50] if len(utt['text']) > 50 else utt['text'])
            if text_hash not in seen_hashes:
                seen_hashes.add(text_hash)
                unique_selected.append(utt)

        # 시간순 정렬 후 반환
        unique_selected.sort(key=lambda x: x.get('start', x.get('idx', 0)))
        return unique_selected[:max_total]

    @traceable(name="generate_speaker_nickname", run_type="llm")
    def call_llm_for_nickname(
        self,
        prompt: str,
        speaker_id: str,
        max_retries: int = RETRY_MAX_ATTEMPTS
    ) -> Optional[Dict]:
        """
        LLM 호출하여 닉네임 생성

        Args:
            prompt: LLM 프롬프트
            speaker_id: 화자 ID
            max_retries: 최대 재시도 횟수

        Returns:
            LLM 응답 결과 (JSON 파싱된 딕셔너리) 또는 None
        """
        # 재시도 루프
        for attempt in range(max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    max_tokens=500
                )

                result = json.loads(response.choices[0].message.content)
                logger.info(f"✓ 닉네임 생성 성공: {speaker_id} -> {result.get('display_label', 'Unknown')}")
                return result

            except Exception as e:
                if attempt < max_retries:
                    wait_time = RETRY_BACKOFF_BASE ** attempt
                    logger.warning(f"⚠️ Retry {attempt+1}/{max_retries} for {speaker_id} after {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    # 최종 실패 - JSON 추출 시도
                    try:
                        error_str = str(e)
                        json_match = re.search(r'\{[^{}]*\}', error_str, re.DOTALL)
                        if json_match:
                            return json.loads(json_match.group())
                    except:
                        pass

                    logger.error(f"❌ 닉네임 생성 실패: {speaker_id} - {str(e)[:100]}")
                    return None

    def process_speakers_for_nicknames(
        self,
        segments: List[Dict]
    ) -> Dict[str, Dict]:
        """
        모든 화자에 대해 닉네임 생성
        
        Args:
            segments: STT 세그먼트 리스트 [{"text": str, "start": float, "end": float, "speaker": str}, ...]
            
        Returns:
            {speaker_label: {nickname, nickname_metadata}, ...}
        """
        logger.info(f"닉네임 태깅 시작: {len(segments)}개 세그먼트")

        # 1. 화자별로 그룹화
        speakers = {}
        for i, segment in enumerate(segments):
            speaker = segment.get('speaker', 'UNKNOWN')
            if speaker not in speakers:
                speakers[speaker] = []
            speakers[speaker].append({
                'idx': i,
                'text': segment.get('text', ''),
                'start': segment.get('start', 0),
                'end': segment.get('end', 0)
            })

        logger.info(f"발견된 화자 수: {len(speakers)}")

        # 2. 비용 추정 (로깅만, 실제로는 진행)
        valid_speakers = {k: v for k, v in speakers.items() if len(v) >= MIN_UTTERANCES}
        if not valid_speakers:
            logger.warning("⚠️ 충분한 발화가 있는 화자가 없습니다.")
            return {}

        # 3. 각 화자에 대해 닉네임 생성
        results = {}
        for idx, (speaker_id, utts) in enumerate(valid_speakers.items(), 1):
            if len(utts) < MIN_UTTERANCES:
                logger.info(f"⏭️ {speaker_id} 스킵 (발화 수 부족: {len(utts)}개)")
                continue

            logger.info(f"[{idx}/{len(valid_speakers)}] {speaker_id} 분석 중...")

            # Smart selection
            selected = self.smart_selection(utts)
            logger.debug(f"  선택된 발화: {len(selected)}개")

            # 프롬프트 생성
            utterances_text = "\n".join([
                f"[#{u['idx']}] {u['text']}" for u in selected
            ])

            prompt = PROMPT_TEMPLATE.format(
                speaker_id=speaker_id,
                total_utterances=len(utts),
                selected_utterances=len(selected),
                utterances_text=utterances_text
            )

            # LLM 호출
            result = self.call_llm_for_nickname(prompt, speaker_id)

            if result:
                # evidence_utter_idx 유효성 검사
                max_idx = len(utts)
                if 'evidence_utter_idx' in result:
                    valid_indices = [idx for idx in result['evidence_utter_idx'] if 0 <= idx < max_idx]
                    result['evidence_utter_idx'] = valid_indices

                results[speaker_id] = {
                    'nickname': result.get('display_label', 'Unknown'),
                    'nickname_metadata': {
                        'display_label': result.get('display_label'),
                        'one_liner': result.get('one_liner'),
                        'keywords': result.get('keywords', []),
                        'communication_style': result.get('communication_style', []),
                        'stance_markers': result.get('stance_markers', []),
                        'evidence_utter_idx': result.get('evidence_utter_idx', [])
                    }
                }
                logger.info(f"  ✓ 성공: '{result.get('display_label', 'Unknown')}'")
            else:
                logger.warning(f"  ❌ {speaker_id} 닉네임 생성 실패")

            # Rate limiting
            if idx < len(valid_speakers):
                time.sleep(DELAY_BETWEEN_BATCHES)

        logger.info(f"✓ 닉네임 태깅 완료: {len(results)}개 화자")
        return results


# 싱글톤 인스턴스
_nickname_service_instance: Optional[NicknameService] = None


def get_nickname_service() -> NicknameService:
    """NicknameService 싱글톤 인스턴스 반환"""
    global _nickname_service_instance
    if _nickname_service_instance is None:
        _nickname_service_instance = NicknameService()
    return _nickname_service_instance

