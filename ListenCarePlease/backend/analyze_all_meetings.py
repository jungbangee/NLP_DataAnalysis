"""
기존 완료된 모든 회의에 대해 효율성 분석을 일괄 실행하는 스크립트
"""
import sys
import time
from app.db.base import SessionLocal
from app.models.audio_file import AudioFile
from app.models.efficiency import MeetingEfficiencyAnalysis
from app.services.efficiency_analyzer import EfficiencyAnalyzer
from datetime import datetime, timezone

def analyze_all_completed_meetings():
    """완료된 모든 회의에 대해 효율성 분석 실행"""
    db = SessionLocal()
    try:
        # 완료된 모든 오디오 파일 조회
        completed_files = db.query(AudioFile).filter(
            AudioFile.status == 'completed'
        ).all()

        print(f"✅ 완료된 회의 {len(completed_files)}개 발견")

        analyzed_count = 0
        skipped_count = 0
        error_count = 0

        for i, audio_file in enumerate(completed_files, 1):
            print(f"\n[{i}/{len(completed_files)}] 처리 중: {audio_file.original_filename} (ID: {audio_file.id})")

            # 이미 분석이 있는지 확인
            existing = db.query(MeetingEfficiencyAnalysis).filter(
                MeetingEfficiencyAnalysis.audio_file_id == audio_file.id
            ).first()

            if existing:
                print(f"  ⏭️  이미 분석 완료 (건너뛰기)")
                skipped_count += 1
                continue

            try:
                # 효율성 분석 실행
                print(f"  🔄 효율성 분석 시작...")
                analyzer = EfficiencyAnalyzer(audio_file.id, db)
                analysis = analyzer.analyze_all()

                # DB에 저장
                db.add(analysis)
                db.commit()
                db.refresh(analysis)

                print(f"  ✅ 분석 완료! 엔트로피 평균: {analysis.entropy_avg:.3f}")
                analyzed_count += 1

                # 과부하 방지를 위해 잠시 대기
                time.sleep(0.5)

            except Exception as e:
                print(f"  ❌ 분석 실패: {e}")
                error_count += 1
                db.rollback()
                continue

        print(f"\n" + "="*60)
        print(f"📊 일괄 분석 완료!")
        print(f"  - 새로 분석됨: {analyzed_count}개")
        print(f"  - 이미 분석됨 (건너뜀): {skipped_count}개")
        print(f"  - 실패: {error_count}개")
        print(f"  - 총 처리: {len(completed_files)}개")
        print("="*60)

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    print("="*60)
    print("🚀 전체 회의 효율성 분석 일괄 실행 스크립트")
    print("="*60)
    analyze_all_completed_meetings()
