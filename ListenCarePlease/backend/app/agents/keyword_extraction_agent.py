"""
키워드 추출 에이전트

비전공자용 전문용어 추출 및 용어집 생성
- 기술/전문 용어 자동 추출
- 동의어/오타 병합
- 중요도 스코어링 (1-10점, 7점 이상만 사용)
- GPT-4o 사용
"""
import json
import re
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.config import settings

KEYWORD_EXTRACTION_PROMPT = """
[Role] 전문 용어 분석가
[Task] 아래 텍스트에서 비전공자가 모를 법한 핵심 전문용어/신조어/약어를 **개수 제한 없이 가능한 많이** 추출하십시오.

[Strict Rules]
1. **Focus:** '회의', '진행' 같은 일상어는 제외하고, **기술/전문 용어**에만 집중하십시오.
2. **Merging:** 뜻이 같은 오타나 변형들은 `synonyms`에 묶으십시오.
3. **No Translation:** 영문 약어(STT)는 **영문 그대로** 추출하십시오. 한글로 번역하지 마십시오.
4. **Typo Fix Only:** 오직 철자 오류만 교정하십시오.
5. **Scoring:** 각 단어의 중요도를 **1~10점**으로 매기십시오. (7점 이상만 사용됨)
   - 10~9점: 이 회의의 핵심 주제어 (반드시 알아야 함)
   - 8~7점: 중요한 기술 용어 또는 개념
   - 6점 이하: 알면 좋지만 몰라도 문맥 파악 가능한 단어

[Output Format]
JSON 리스트만 출력:
[
    {{
        "clean_word": "본문에 넣을 단어 (원문 언어 유지)",
        "synonyms": ["본문 오타1", "원본단어"],
        "glossary_display": "해설집용 표기 (예: STT (Speech To Text))",
        "mean": "설명",
        "importance": 9
    }}
]

[Text]
{text}
"""


class AgentState(TypedDict):
    text: str
    extracted_keywords: Optional[List[Dict[str, Any]]]
    error: Optional[str]


def extract_keywords(state: AgentState) -> AgentState:
    """LLM을 호출하여 키워드 추출"""
    text = state["text"]
    truncated_text = text[:60000]

    prompt = KEYWORD_EXTRACTION_PROMPT.format(text=truncated_text)
    llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=settings.OPENAI_API_KEY)

    try:
        response = llm.invoke([HumanMessage(content=prompt)])

        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]

        data = json.loads(content)
        return {"extracted_keywords": data}

    except Exception as e:
        return {"error": str(e)}


def create_keyword_extraction_agent():
    """키워드 추출 LangGraph 워크플로우 생성"""
    workflow = StateGraph(AgentState)

    workflow.add_node("extract_keywords", extract_keywords)

    workflow.set_entry_point("extract_keywords")
    workflow.add_edge("extract_keywords", END)

    return workflow.compile()


async def run_keyword_extraction_agent(text: str) -> List[Dict[str, Any]]:
    """
    키워드 추출 에이전트 실행

    Args:
        text: 분석할 텍스트 (최대 60,000자)

    Returns:
        추출된 키워드 리스트
    """
    agent = create_keyword_extraction_agent()

    initial_state = {
        "text": text,
        "extracted_keywords": None,
        "error": None
    }

    result = await agent.ainvoke(initial_state)

    if result.get("error"):
        raise Exception(f"Keyword extraction failed: {result['error']}")

    return result["extracted_keywords"]
