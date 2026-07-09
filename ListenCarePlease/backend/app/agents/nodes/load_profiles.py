"""
load_profiles_node
기존 화자 프로필 로드
"""
from app.agents.state import AgentState
from app.db.base import SessionLocal
from app.models.speaker_profile import SpeakerProfile


async def load_profiles_node(state: AgentState) -> AgentState:
    """
    speaker_profiles DB에서 사용자의 기존 프로필들을 로드합니다.
    """
    user_id = state.get("user_id")

    if not user_id:
        state["previous_profiles"] = []
        return state

    # DB 세션 생성
    db = SessionLocal()

    try:
        # 해당 사용자의 모든 화자 프로필 조회
        profiles = db.query(SpeakerProfile).filter(
            SpeakerProfile.user_id == user_id
        ).all()

        # 툴콜링 형식에 맞게 변환
        previous_profiles = []
        for profile in profiles:
            previous_profiles.append({
                "name": profile.speaker_name,
                "voice_embedding": profile.voice_embedding,
                "text_embedding": profile.text_embedding,
                "sample_texts": profile.sample_texts or [],
                "confidence_score": profile.confidence_score
            })

        state["previous_profiles"] = previous_profiles
        print(f"✅ 프로필 {len(previous_profiles)}개 로드 완료 (user_id={user_id})")

    except Exception as e:
        print(f"⚠️ 프로필 로드 실패: {e}")
        state["previous_profiles"] = []
    finally:
        db.close()

    return state

