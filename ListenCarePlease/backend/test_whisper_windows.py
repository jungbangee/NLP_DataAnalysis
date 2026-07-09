"""
Windows에서 Whisper 메모리 에러 테스트 스크립트

사용법:
1. 가상환경 활성화 (conda 또는 venv)
2. python test_whisper_windows.py

테스트 항목:
- 로컬 Whisper 모델 로딩 (tiny, base, small)
- 짧은 오디오 파일 전사
- 메모리 사용량 모니터링
"""

import os
import sys
import psutil
import time
from pathlib import Path

# 메모리 사용량 출력
def print_memory_usage():
    process = psutil.Process()
    mem_info = process.memory_info()
    mem_mb = mem_info.rss / 1024 / 1024
    print(f"💾 현재 메모리 사용량: {mem_mb:.1f} MB")
    return mem_mb


def test_whisper_import():
    """Whisper 라이브러리 import 테스트"""
    print("\n" + "="*60)
    print("TEST 1: Whisper 라이브러리 import")
    print("="*60)

    try:
        import whisper
        print("✅ openai-whisper 설치됨")
        print(f"   버전: {whisper.__version__}")
        return True
    except ImportError as e:
        print("❌ openai-whisper 설치 안됨")
        print(f"   에러: {e}")
        print("\n설치 방법:")
        print("  pip install openai-whisper")
        return False


def test_model_loading(model_sizes=["tiny", "base"]):
    """모델 로딩 테스트"""
    print("\n" + "="*60)
    print("TEST 2: Whisper 모델 로딩 테스트")
    print("="*60)

    try:
        import whisper
        import torch
    except ImportError:
        print("❌ 필요한 라이브러리가 없습니다.")
        return False

    print(f"🖥️  디바이스: CPU")
    print(f"🔢 Torch 버전: {torch.__version__}")
    print_memory_usage()

    results = {}

    for model_size in model_sizes:
        print(f"\n{'─'*60}")
        print(f"모델: {model_size}")
        print(f"{'─'*60}")

        try:
            print(f"📥 {model_size} 모델 로딩 중...")
            start_time = time.time()
            start_mem = print_memory_usage()

            model = whisper.load_model(model_size, device="cpu")

            elapsed = time.time() - start_time
            end_mem = print_memory_usage()
            mem_increase = end_mem - start_mem

            print(f"✅ 로딩 완료")
            print(f"   소요 시간: {elapsed:.1f}초")
            print(f"   메모리 증가: +{mem_increase:.1f} MB")

            results[model_size] = {
                "success": True,
                "time": elapsed,
                "memory": mem_increase
            }

            # 메모리 해제
            del model
            import gc
            gc.collect()

            time.sleep(1)

        except Exception as e:
            print(f"❌ 로딩 실패")
            print(f"   에러: {e}")
            results[model_size] = {
                "success": False,
                "error": str(e)
            }

    # 결과 요약
    print("\n" + "="*60)
    print("📊 모델 로딩 결과 요약")
    print("="*60)
    for model_size, result in results.items():
        if result["success"]:
            print(f"✅ {model_size:10s}: {result['time']:5.1f}초, {result['memory']:6.1f} MB")
        else:
            print(f"❌ {model_size:10s}: {result['error']}")

    return results


def test_transcription():
    """실제 전사 테스트"""
    print("\n" + "="*60)
    print("TEST 3: 오디오 전사 테스트")
    print("="*60)

    # 테스트 오디오 파일 확인
    test_audio = Path("test_audio.wav")
    if not test_audio.exists():
        print("⚠️  테스트 오디오 파일이 없습니다.")
        print("   test_audio.wav 파일을 준비하고 다시 실행하세요.")
        return False

    try:
        import whisper
    except ImportError:
        print("❌ openai-whisper가 설치되지 않았습니다.")
        return False

    print(f"🎵 테스트 파일: {test_audio}")
    print_memory_usage()

    try:
        print("\n📥 tiny 모델 로딩...")
        model = whisper.load_model("tiny", device="cpu")
        print_memory_usage()

        print("\n▶️  전사 시작...")
        start_time = time.time()

        result = model.transcribe(
            str(test_audio),
            language="ko",
            verbose=False
        )

        elapsed = time.time() - start_time
        print(f"✅ 전사 완료 ({elapsed:.1f}초)")
        print_memory_usage()

        print("\n📝 전사 결과:")
        print(f"   {result['text']}")

        return True

    except Exception as e:
        print(f"❌ 전사 실패")
        print(f"   에러: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_memory_limit():
    """메모리 제한 테스트"""
    print("\n" + "="*60)
    print("TEST 4: 메모리 제한 확인")
    print("="*60)

    process = psutil.Process()
    mem_info = process.memory_info()

    # 시스템 메모리 정보
    virtual_mem = psutil.virtual_memory()

    print(f"💾 시스템 메모리:")
    print(f"   총 메모리: {virtual_mem.total / 1024 / 1024 / 1024:.1f} GB")
    print(f"   사용 가능: {virtual_mem.available / 1024 / 1024 / 1024:.1f} GB")
    print(f"   사용률: {virtual_mem.percent}%")

    print(f"\n💾 현재 프로세스:")
    print(f"   메모리 사용: {mem_info.rss / 1024 / 1024:.1f} MB")

    # 권장 모델 크기
    available_gb = virtual_mem.available / 1024 / 1024 / 1024

    print(f"\n💡 권장 모델:")
    if available_gb < 2:
        print(f"   ⚠️  사용 가능 메모리 부족 ({available_gb:.1f} GB)")
        print(f"   권장: tiny 또는 base 모델")
    elif available_gb < 4:
        print(f"   tiny, base, small 모델 사용 가능")
    elif available_gb < 8:
        print(f"   tiny ~ medium 모델 사용 가능")
    else:
        print(f"   모든 모델 사용 가능")


def main():
    print("="*60)
    print("🪟 Windows Whisper 메모리 테스트")
    print("="*60)

    # 플랫폼 확인
    print(f"\n🖥️  운영체제: {sys.platform}")
    print(f"🐍 Python 버전: {sys.version}")

    # TEST 1: Import
    if not test_whisper_import():
        print("\n❌ Whisper가 설치되지 않았습니다. 테스트 중단.")
        return

    # TEST 2: 모델 로딩
    test_model_loading(["tiny", "base"])

    # TEST 3: 전사 (선택적)
    # test_transcription()

    # TEST 4: 메모리 확인
    test_memory_limit()

    # 최종 권장사항
    print("\n" + "="*60)
    print("📌 권장사항")
    print("="*60)
    print("1. 메모리 에러가 발생하면 작은 모델 사용:")
    print("   - WHISPER_MODEL_SIZE=tiny")
    print("   - WHISPER_MODEL_SIZE=base")
    print("")
    print("2. .env 파일에서 설정 변경:")
    print("   WHISPER_MODE=local")
    print("   WHISPER_MODEL_SIZE=base")
    print("   WHISPER_DEVICE=cpu")
    print("")
    print("3. 메모리 부족 시 API 사용:")
    print("   WHISPER_MODE=api")
    print("   OPENAI_API_KEY=your-api-key")


if __name__ == "__main__":
    main()
