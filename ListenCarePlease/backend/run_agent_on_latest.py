"""
최신 처리된 파일에 대해 Agent 실행
DB에 저장된 최신 처리 결과를 불러와서 LangGraph Agent 실행
"""
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.db.base import SessionLocal
from app.models.audio_file import AudioFile
from app.models.tagging import SpeakerMapping
from app.services.agent_data_loader import load_agent_input_data
from app.agents.graph import get_speaker_tagging_app
from sqlalchemy import desc


async def run_agent_on_latest():
    """
    최신 처리된 파일에 대해 Agent 실행
    """
    db = SessionLocal()
    
    try:
        # 1. 최신 처리된 AudioFile 찾기
        audio_file = db.query(AudioFile).order_by(
            desc(AudioFile.created_at)
        ).first()
        
        if not audio_file:
            print("❌ 처리된 파일을 찾을 수 없습니다.")
            return
        
        print(f"📁 파일 찾음: {audio_file.original_filename}")
        print(f"   ID: {audio_file.id}")
        print(f"   생성일: {audio_file.created_at}")
        
        # 2. 이미 Agent가 실행되었는지 확인
        existing_mappings = db.query(SpeakerMapping).filter(
            SpeakerMapping.audio_file_id == audio_file.id,
            SpeakerMapping.suggested_name.isnot(None)
        ).count()
        
        if existing_mappings > 0:
            print(f"⚠️  이미 Agent가 실행된 파일입니다. (매핑 {existing_mappings}개 존재)")
            response = input("다시 실행하시겠습니까? (y/n): ")
            if response.lower() != 'y':
                print("취소되었습니다.")
                return
        
        # 3. DB에서 데이터 로드
        print("\n📊 DB에서 데이터 로드 중...")
        agent_input = load_agent_input_data(audio_file.id, db)
        
        print(f"   - STT 세그먼트: {len(agent_input['stt_result'])}개")
        print(f"   - 화자 수: {len(agent_input['diar_result']['embeddings'])}개")
        print(f"   - 이름 언급: {len(agent_input['name_mentions'])}개")
        print(f"   - 참여자 이름: {agent_input.get('participant_names', [])}")
        
        if not agent_input.get('participant_names'):
            print("⚠️  참여자 이름이 없습니다. UserConfirmation을 먼저 설정해주세요.")
            return
        
        # 4. AgentState 구성
        print("\n🤖 Agent 실행 중...")
        initial_state = {
            "user_id": audio_file.user_id,
            "audio_file_id": audio_file.id,
            "stt_result": agent_input["stt_result"],
            "diar_result": agent_input["diar_result"],
            "participant_names": agent_input.get("participant_names", []),
            "previous_profiles": [],
            "auto_matched": {},
            "name_mentions": agent_input["name_mentions"],
            "speaker_utterances": {},
            "mapping_history": [],
            "name_based_results": {},
            "final_mappings": {},
            "needs_manual_review": []
        }
        
        # 5. Agent 실행
        app = get_speaker_tagging_app()
        final_state = await app.ainvoke(initial_state)
        
        # 6. 결과를 SpeakerMapping 테이블에 저장
        print("\n💾 결과 저장 중...")
        final_mappings = final_state.get("final_mappings", {})
        
        saved_count = 0
        for speaker_label, mapping_info in final_mappings.items():
            # 기존 SpeakerMapping 찾기
            speaker_mapping = db.query(SpeakerMapping).filter(
                SpeakerMapping.audio_file_id == audio_file.id,
                SpeakerMapping.speaker_label == speaker_label
            ).first()
            
            if speaker_mapping:
                # 업데이트
                speaker_mapping.suggested_name = mapping_info.get("name")
                speaker_mapping.name_confidence = mapping_info.get("confidence")
                speaker_mapping.name_mentions = len([
                    m for m in final_state.get("name_mentions", [])
                    if m.get("name") == mapping_info.get("name")
                ])
                speaker_mapping.needs_manual_review = mapping_info.get("needs_review", False)
                speaker_mapping.conflict_detected = False
            else:
                # 새로 생성
                speaker_mapping = SpeakerMapping(
                    audio_file_id=audio_file.id,
                    speaker_label=speaker_label,
                    suggested_name=mapping_info.get("name"),
                    name_confidence=mapping_info.get("confidence"),
                    name_mentions=len([
                        m for m in final_state.get("name_mentions", [])
                        if m.get("name") == mapping_info.get("name")
                    ]),
                    suggested_role=None,
                    role_confidence=None,
                    conflict_detected=False,
                    needs_manual_review=mapping_info.get("needs_review", False),
                    final_name="",
                    is_modified=False
                )
                db.add(speaker_mapping)
            
            saved_count += 1
        
        db.commit()
        
        # 7. 결과 출력
        print(f"\n✅ Agent 실행 완료!")
        print(f"   - 저장된 매핑: {saved_count}개")
        print(f"\n📋 매핑 결과:")
        for speaker_label, mapping_info in final_mappings.items():
            name = mapping_info.get("name", "Unknown")
            confidence = mapping_info.get("confidence", 0.0)
            needs_review = mapping_info.get("needs_review", False)
            review_mark = "⚠️" if needs_review else "✅"
            print(f"   {review_mark} {speaker_label} → {name} (신뢰도: {confidence:.2f})")
        
        if final_state.get("needs_manual_review"):
            print(f"\n⚠️  수동 확인 필요한 화자: {final_state['needs_manual_review']}")
        
    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_agent_on_latest())

