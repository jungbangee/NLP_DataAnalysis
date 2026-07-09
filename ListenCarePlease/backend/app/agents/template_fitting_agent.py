"""
템플릿 피팅 에이전트

회의 유형별 자동 구조화 시스템
- 6가지 회의 유형 지원 (informing, checking_syncing, problem_solving, plan_design, decide_commit, relationship_review)
- 주제 변화 지점 자동 감지하여 Section 분할
- 각 Section별 discussion_summary, decisions, action_items 생성
- GPT-4o-mini 사용
"""
import json
import os
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.config import settings

MEETING_TYPE_MAP = {
    "a": "informing",
    "b": "checking_syncing",
    "c": "problem_solving",
    "d": "plan_design",
    "e": "decide_commit",
    "f": "relationship_review",
}

TYPE_SPEC_HINTS = {
    "informing": """
- 정보 전달이 핵심인 회의입니다.
- 주요 공지사항, 변화된 점, 대상자, Q&A 요약에 초점을 맞추세요.
- action_items는 가벼운 follow-up 위주로 작성하세요.
""",
    "checking_syncing": """
- 진행 상황 점검 및 정렬을 위한 회의입니다.
- 'Planned vs Actual', 'Blockers', 'Follow-up Checks'를 요약하세요.
- action_items에는 다음 체크포인트를 명확히 적으세요.
""",
    "problem_solving": """
- 문제 정의와 아이디어 탐색이 핵심입니다.
- problem_statement를 명확히 쓰고, 주요 아이디어/가설과 pros & cons를 담으세요.
- decisions는 tentative 결정 위주로 적으세요.
""",
    "plan_design": """
- 계획 수립 및 설계가 목적입니다.
- objectives, deliverables, timeline을 반영하세요.
- action_items는 '누가, 무엇을, 언제까지' 형식으로 작성하세요.
""",
    "decide_commit": """
- 공식적인 결정과 합의가 일어나는 회의입니다.
- decisions와 rationale에 비중을 두세요.
- action_items는 결정 실행을 위한 구체적인 작업으로 작성하세요.
""",
    "relationship_review": """
- 피드백, 감정 공유, 관계 정리가 중심인 회의입니다.
- discussion_summary에 분위기와 핵심 피드백을 요약하세요.
- action_items에는 향후 행동 약속이 있다면 포함하세요.
"""
}

COMMON_JSON_SCHEMA_DESCRIPTION = """
반드시 아래 키들을 포함하는 JSON 객체를 출력하세요.

{
  "metadata": {
    "title": string,
    "meeting_type": string,
    "generated_by": string,
    "model": string
  },
  "summary": {
    "overall": string,
    "key_takeaways": string[]
  },
  "sections": [
    {
      "section_title": string,
      "start_index": integer,
      "end_index": integer,
      "meeting_type": string,
      "discussion_summary": string,
      "decisions": string[],
      "action_items": [
        {
          "owner": string | null,
          "task": string,
          "due": string | null
        }
      ]
    }
  ]
}
"""


class AgentState(TypedDict):
    transcript_segments: List[Dict[str, Any]]
    speaker_mapping: Dict[str, str]
    meeting_type: str
    meeting_text: str
    generated_json: Optional[Dict[str, Any]]
    error: Optional[str]


def format_transcript(state: AgentState) -> AgentState:
    """대화 내용을 [Index] [Speaker] Text 형식으로 변환"""
    segments = state["transcript_segments"]
    speaker_map = state["speaker_mapping"]

    lines = []
    for idx, seg in enumerate(segments):
        spk = seg.get("speaker") or seg.get("speaker_label") or "UNKNOWN"
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        display = speaker_map.get(spk, spk)
        lines.append(f"[{idx}] [{display}] {text}")

    return {"meeting_text": "\n".join(lines)}


def generate_minutes(state: AgentState) -> AgentState:
    """LLM을 호출하여 회의록 JSON 생성 (Section 분할 포함)"""
    meeting_type_code = state["meeting_type"]
    mt = MEETING_TYPE_MAP.get(meeting_type_code, meeting_type_code)
    if mt not in TYPE_SPEC_HINTS:
        mt = "plan_design"

    type_hint = TYPE_SPEC_HINTS.get(mt, "")
    meeting_text = state["meeting_text"]

    system_prompt = (
        "당신은 회의록 작성 및 '구간 분석(Segmentation)' 전문가입니다. "
        "제공된 회의 대화를 읽고, 주제가 바뀌는 지점을 파악하여 여러 개의 'Section'으로 나누어야 합니다. "
        "각 Section별로 시작 인덱스(start_index)와 끝 인덱스(end_index)를 정확히 명시하세요. "
        "반드시 JSON만 출력하세요."
    )

    user_prompt = (
        f"회의 유형: {mt}\n\n"
        "아래는 인덱스가 포함된 회의 대화입니다. ([Index] [Speaker] Text 형식)\n"
        "----- 회의 대화 시작 -----\n"
        f"{meeting_text}\n"
        "----- 회의 대화 끝 -----\n\n"
        "요구사항:\n"
        "1. 전체 대화를 논리적인 주제 단위(Section)로 나누세요.\n"
        "2. 각 Section의 `start_index`와 `end_index`는 위 대화의 [Index] 번호를 참조해야 합니다.\n"
        "3. 모든 발화가 빠짐없이 Section에 포함되도록 하세요 (연속적이어야 함).\n"
        f"{type_hint}\n"
        "다음 JSON 스키마를 따르세요:\n"
        f"{COMMON_JSON_SCHEMA_DESCRIPTION}\n"
    )

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1, api_key=settings.OPENAI_API_KEY)

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])

        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]

        data = json.loads(content)
        return {"generated_json": data}

    except Exception as e:
        return {"error": str(e)}


def create_template_fitting_agent():
    """템플릿 피팅 LangGraph 워크플로우 생성"""
    workflow = StateGraph(AgentState)

    workflow.add_node("format_transcript", format_transcript)
    workflow.add_node("generate_minutes", generate_minutes)

    workflow.set_entry_point("format_transcript")
    workflow.add_edge("format_transcript", "generate_minutes")
    workflow.add_edge("generate_minutes", END)

    return workflow.compile()


async def run_template_fitting_agent(
    transcript_segments: List[Dict[str, Any]],
    speaker_mapping: Dict[str, str],
    meeting_type: str = "d"
) -> Dict[str, Any]:
    """
    템플릿 피팅 에이전트 실행

    Args:
        transcript_segments: 대화 세그먼트 리스트
        speaker_mapping: 화자 매핑 {"SPEAKER_00": "김민서"}
        meeting_type: 회의 유형 (a-f)

    Returns:
        생성된 회의록 JSON
    """
    agent = create_template_fitting_agent()

    initial_state = {
        "transcript_segments": transcript_segments,
        "speaker_mapping": speaker_mapping,
        "meeting_type": meeting_type,
        "meeting_text": "",
        "generated_json": None,
        "error": None
    }

    result = await agent.ainvoke(initial_state)

    if result.get("error"):
        raise Exception(f"Template fitting failed: {result['error']}")

    return result["generated_json"]
