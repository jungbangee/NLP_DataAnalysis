"""
name_based_tagging_node
이름 기반 화자 태깅 (대화흐름.ipynb 로직 재사용)
"""
from typing import List, Dict
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from app.core.config import settings
from app.agents.state import AgentState
from app.agents.prompts.name_based_prompt import create_name_based_prompt


class SpeakerMappingResult(BaseModel):
    """LLM 응답 파싱용 모델"""
    speaker: str = Field(description="Speaker ID (예: SPEAKER_00)")
    name: str = Field(description="참여자 이름 (반드시 system 프롬프트의 '참여자 이름 목록'에 있는 이름 중 하나여야 함)")
    confidence: float = Field(description="확신도 0.0~1.0", ge=0.0, le=1.0)
    reasoning: str = Field(description="판단 근거")


async def name_based_tagging_node(state: AgentState) -> AgentState:
    """
    방식1: 이름 기반 태깅
    - LLM에게 대화 흐름을 보여주고 "민서는 SPEAKER_00? SPEAKER_01?" 판단
    - 대화흐름.ipynb의 LangChainSpeakerMapper 로직 재사용
    """
    import os
    name_mentions = state.get("name_mentions", [])
    participant_names = state.get("participant_names", [])
    mapping_history = state.get("mapping_history", [])
    
    if not name_mentions:
        state["name_based_results"] = {}
        return state

    # LangSmith 추적 환경 변수 확인 및 조정 (API 키가 없으면 비활성화)
    langchain_tracing = os.getenv("LANGCHAIN_TRACING_V2", "false")
    if langchain_tracing.lower() == "true":
        # LANGSMITH_API_KEY도 확인 (일부 설정에서 사용)
        langchain_api_key = os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY")
        if langchain_api_key and langchain_api_key.strip():
            # LANGCHAIN_API_KEY가 없으면 LANGSMITH_API_KEY를 복사
            if not os.getenv("LANGCHAIN_API_KEY") and os.getenv("LANGSMITH_API_KEY"):
                os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY")
        else:
            # API 키가 없으면 추적 비활성화 (에러 방지)
            os.environ["LANGCHAIN_TRACING_V2"] = "false"

    # LLM 초기화
    # LLM 초기화
    # gpt-5-mini 모델은 temperature 기본값(1)만 지원하므로 명시적으로 설정
    model_name = "gpt-5-mini-2025-08-07"
    
    print(f"🔍 [NameBasedTagging] Processing {len(name_mentions)} name mentions using {model_name}")

    # temperature 설정
    # gpt-5-mini는 기본값(1)만 지원하므로 temperature=1 명시
    # 다른 모델은 temperature=0.3 사용
    if model_name.startswith("gpt-5-mini"):
        llm = ChatOpenAI(
            model=model_name,
            temperature=1.0,  # gpt-5-mini는 기본값(1)만 지원
            api_key=settings.OPENAI_API_KEY
        )
    else:
        llm = ChatOpenAI(
            model=model_name,
            temperature=0.3,
            api_key=settings.OPENAI_API_KEY
        )

    # PydanticOutputParser 초기화
    output_parser = PydanticOutputParser(pydantic_object=SpeakerMappingResult)
    format_instructions = output_parser.get_format_instructions()

    name_results = {}
    
    # 각 이름 언급에 대해 LLM 호출 (대화흐름.ipynb와 동일하게)
    for turn_num, mention in enumerate(name_mentions, 1):
        name = mention.get("name")
        context_before = mention.get("context_before", [])
        context_after = mention.get("context_after", [])
        time_detected = mention.get("time", 0.0)
        target_text = mention.get("target_text")  # 실제 이름이 언급된 문장
        target_speaker = mention.get("target_speaker")  # target 문장의 화자

        # 프롬프트 생성
        system_message, user_message = create_name_based_prompt(
            name=name,
            context_before=context_before,
            context_after=context_after,
            participant_names=participant_names,
            mapping_history=mapping_history,
            turn_num=turn_num,
            format_instructions=format_instructions,
            target_text=target_text,
            target_speaker=target_speaker
        )

        try:
            # LLM 호출
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ]

            # LLM 호출 (LangChain 사용 - LangSmith 자동 추적)
            response = llm.invoke(messages)
            response_content = response.content
            
            result_obj = output_parser.parse(response_content)

            result = {
                "speaker": result_obj.speaker,
                "name": result_obj.name,
                "confidence": result_obj.confidence,
                "reasoning": result_obj.reasoning,
                "turn": turn_num,
                "time": time_detected,
                "name_mentioned": name
            }

            # mapping_history에 추가
            mapping_history.append(result)

            # 같은 이름에 대한 여러 결과를 리스트로 저장
            if name not in name_results:
                name_results[name] = []
            name_results[name].append(result)

        except Exception as e:
            # 에러 발생 시 기본값 반환
            result = {
                "speaker": "Unknown",
                "name": "Unknown",
                "confidence": 0.0,
                "reasoning": f"에러: {str(e)[:100]}",
                "turn": turn_num,
                "time": time_detected,
                "name_mentioned": name,
                "error": str(e)[:200]
            }
            mapping_history.append(result)

    state["name_based_results"] = name_results
    state["mapping_history"] = mapping_history

    return state

