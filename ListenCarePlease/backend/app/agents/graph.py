"""
LangGraph StateGraph 구성
"""
from langgraph.graph import StateGraph, END
from app.agents.state import AgentState
from app.agents.nodes.load_profiles import load_profiles_node
from app.agents.nodes.embedding_match import embedding_match_node
from app.agents.nodes.name_extraction import name_extraction_node
from app.agents.nodes.name_based_tagging import name_based_tagging_node
from app.agents.nodes.merge_results import merge_results_node


def create_speaker_tagging_graph() -> StateGraph:
    """
    화자 태깅 Graph 생성 및 컴파일
    """
    # Graph 생성
    graph = StateGraph(AgentState)

    # 노드 추가
    graph.add_node("load_profiles", load_profiles_node)
    graph.add_node("embedding_match", embedding_match_node)
    graph.add_node("name_extraction", name_extraction_node)
    graph.add_node("name_based_tagging", name_based_tagging_node)
    graph.add_node("merge_results", merge_results_node)

    # 엣지 설정 (순차 실행)
    graph.add_edge("load_profiles", "embedding_match")
    graph.add_edge("embedding_match", "name_extraction")
    graph.add_edge("name_extraction", "name_based_tagging")
    graph.add_edge("name_based_tagging", "merge_results")
    graph.add_edge("merge_results", END)

    # 진입점 설정
    graph.set_entry_point("load_profiles")

    # 컴파일
    app = graph.compile()

    return app


# 싱글톤 인스턴스
_speaker_tagging_app = None


def get_speaker_tagging_app() -> StateGraph:
    """
    화자 태깅 Graph 앱 싱글톤 인스턴스 반환
    """
    global _speaker_tagging_app

    if _speaker_tagging_app is None:
        _speaker_tagging_app = create_speaker_tagging_graph()

    return _speaker_tagging_app

