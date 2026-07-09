"""
TODO 추출 서비스
회의록에서 날짜/요일 키워드를 찾아 앞뒤 3문장씩 추출 후 GPT로 TODO 생성
"""
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import openai
from app.core.config import settings

# 날짜/요일 관련 키워드
DATE_KEYWORDS = [
    # 상대적 날짜
    r'오늘',
    r'내일',
    r'모레',
    r'글피',
    r'이번\s*주',
    r'다음\s*주',
    r'담주',
    r'차주',

    # 요일
    r'월요일', r'화요일', r'수요일', r'목요일', r'금요일', r'토요일', r'일요일',
    r'월욜', r'화욜', r'수욜', r'목욜', r'금욜', r'토욜', r'일욜',

    # 숫자 + 일/주
    r'\d+일\s*(뒤|후|까지|안)',
    r'\d+주\s*(뒤|후|까지|안)',

    # 날짜 패턴 (11/25, 11월 25일 등)
    r'\d{1,2}월\s*\d{1,2}일',
    r'\d{1,2}/\d{1,2}',
]

def split_into_sentences(text: str) -> List[str]:
    """텍스트를 문장 단위로 분리"""
    # 문장 종결 기호로 분리 (. ! ? 등)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    # 빈 문장 제거
    return [s.strip() for s in sentences if s.strip()]

def find_date_keyword_sentences(text: str) -> List[Dict[str, any]]:
    """
    날짜 키워드가 포함된 문장을 찾고 앞뒤 3문장씩 추출

    Returns:
        [
            {
                'keyword': '내일',
                'sentence_index': 5,
                'context': '...앞 3문장 + 해당 문장 + 뒤 3문장...'
            },
            ...
        ]
    """
    sentences = split_into_sentences(text)
    results = []

    # 중복 방지를 위한 인덱스 세트
    processed_indices = set()

    for keyword_pattern in DATE_KEYWORDS:
        for idx, sentence in enumerate(sentences):
            if re.search(keyword_pattern, sentence) and idx not in processed_indices:
                # 앞뒤 3문장씩 추출 (총 7문장)
                start_idx = max(0, idx - 3)
                end_idx = min(len(sentences), idx + 4)  # idx + 1 + 3

                context_sentences = sentences[start_idx:end_idx]
                context = ' '.join(context_sentences)

                results.append({
                    'keyword': re.search(keyword_pattern, sentence).group(),
                    'sentence_index': idx,
                    'context': context,
                    'matched_sentence': sentence
                })

                processed_indices.add(idx)

    return results

def extract_todos_with_gpt(
    contexts: List[Dict[str, any]],
    meeting_date: str,
    openai_api_key: Optional[str] = None
) -> List[Dict[str, any]]:
    """
    GPT-4o를 사용하여 추출된 컨텍스트에서 TODO 생성

    Args:
        contexts: find_date_keyword_sentences() 결과
        meeting_date: 회의 날짜 (YYYY-MM-DD)
        openai_api_key: OpenAI API Key (없으면 settings에서 가져옴)

    Returns:
        [
            {
                'task': '할 일 내용',
                'assignee': '담당자',
                'due_date': 'YYYY-MM-DD HH:MM',
                'priority': 'High/Medium/Low'
            },
            ...
        ]
    """
    if not contexts:
        return []

    # OpenAI 클라이언트 설정
    api_key = openai_api_key or settings.OPENAI_API_KEY
    if not api_key:
        raise ValueError("OpenAI API key가 설정되지 않았습니다.")

    client = openai.OpenAI(api_key=api_key)

    # 회의 날짜 포맷팅
    try:
        dt_obj = datetime.strptime(meeting_date, "%Y-%m-%d")
        formatted_date = dt_obj.strftime("%Y-%m-%d (%A)")
    except ValueError:
        formatted_date = meeting_date

    # 컨텍스트 텍스트 결합
    combined_text = "\n\n---\n\n".join([
        f"[키워드: {ctx['keyword']}]\n{ctx['context']}"
        for ctx in contexts
    ])

    system_prompt = f"""
당신은 전문적인 '회의록 분석 비서'입니다.
제공된 회의록 텍스트 일부를 분석하여 '실행 가능한 할 일(To-Do List)'을 JSON 형식으로 추출하세요.

[중요: 기준 날짜]
{formatted_date}

**모든 상대적 날짜(내일, 모레, 다음 주 등)는 위 '기준 날짜'를 기점(Today)으로 계산해야 합니다.**
(예: 기준일이 11월 6일(목)이고 "내일까지"라고 하면 -> 11월 7일로 계산)

[추출 규칙]
1. 명확하게 담당자가 지정되고, 실행하기로 합의된 안건만 추출하세요.
2. **마감 기한(due_date)은 반드시 'YYYY-MM-DD HH:MM' 형식(24시간제)으로 변환하세요.**
   - 예: "오후 2시까지" -> "{meeting_date} 14:00"
3. **시간이 명시되지 않은 경우의 처리:**
   - 구체적인 시간이 없고 날짜만 있다면, 업무 마감 시간인 '18:00'로 설정하세요.
4. 모호하거나 거절된 요청은 제외하세요.
5. 담당자를 알 수 없는 경우 "미지정"으로 표시하세요.

[출력 형식 - JSON]
{{
    "todos": [
        {{
            "task": "할 일 내용",
            "assignee": "담당자 이름",
            "due_date": "YYYY-MM-DD HH:MM",
            "priority": "High/Medium/Low"
        }}
    ]
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"다음 회의록 일부에서 To-Do를 추출해줘:\n\n{combined_text}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            seed=1234
        )

        import json
        result = json.loads(response.choices[0].message.content)
        return result.get('todos', [])

    except Exception as e:
        print(f"GPT 요청 중 오류 발생: {e}")
        raise

def extract_todos_from_transcript(
    transcript_text: str,
    meeting_date: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> List[Dict[str, any]]:
    """
    회의록 전체에서 TODO 추출 (메인 함수)

    Args:
        transcript_text: 회의록 전체 텍스트
        meeting_date: 회의 날짜 (YYYY-MM-DD), None이면 오늘 날짜 사용
        openai_api_key: OpenAI API Key (옵션)

    Returns:
        TODO 리스트
    """
    # 회의 날짜 기본값 설정
    if not meeting_date:
        meeting_date = datetime.now().strftime("%Y-%m-%d")

    # 1. 날짜 키워드 검색 (참고용으로 남겨두거나 제거 가능)
    # 기존 로직은 키워드가 없으면 바로 리턴해버려서, 날짜 언급 없는 TODO를 놓침
    
    # 2. 전체 텍스트 분석으로 변경
    # 토큰 제한을 고려하여 텍스트가 너무 길면 잘라야 할 수도 있음 (GPT-4o는 128k라 웬만하면 됨)
    MAX_CHARS = 50000 
    if len(transcript_text) > MAX_CHARS:
        transcript_text = transcript_text[:MAX_CHARS] + "...(truncated)"

    # GPT에게 전체 텍스트를 주고 TODO 추출 요청
    # 기존 extract_todos_with_gpt 함수를 재사용하되, contexts 구조를 맞추거나 함수를 수정해야 함
    # 여기서는 함수를 수정하는 대신, 전체 텍스트를 하나의 'context'로 포장하여 전달
    
    dummy_context = [{
        'keyword': '전체 회의록',
        'sentence_index': 0,
        'context': transcript_text,
        'matched_sentence': ''
    }]

    todos = extract_todos_with_gpt(dummy_context, meeting_date, openai_api_key)

    return todos
