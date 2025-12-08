"""
ListenCarePlease CLI - 모듈별 독립 실행

각 AI 기능을 커맨드라인에서 독립적으로 실행할 수 있습니다.
"""
import sys
import os
import json
import asyncio
import click
from pathlib import Path

# 백엔드 app을 import할 수 있도록 경로 추가
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.services.stt import run_stt_pipeline
from app.services.diarization import run_diarization
from app.services.todo_extractor import extract_todos_from_transcript
from app.agents.keyword_extraction_agent import run_keyword_extraction_agent
from app.agents.template_fitting_agent import run_template_fitting_agent
from app.core.config import settings


@click.group()
def cli():
    """ListenCarePlease CLI - AI 회의록 생성 도구"""
    pass


@cli.command()
@click.option('--input', '-i', required=True, type=click.Path(exists=True), help='입력 오디오 파일 (WAV)')
@click.option('--output', '-o', required=True, type=click.Path(), help='출력 텍스트 파일')
@click.option('--model', '-m', default='large-v3', help='Whisper 모델 크기 (기본값: large-v3)')
@click.option('--device', '-d', default='cpu', help='디바이스 (cpu/cuda)')
def stt(input, output, model, device):
    """STT - 음성을 텍스트로 변환"""
    click.echo(f"🎤 STT 시작: {input}")

    input_path = Path(input)
    output_path = Path(output)
    work_dir = output_path.parent / f"{input_path.stem}_work"
    work_dir.mkdir(exist_ok=True)

    try:
        result_path = run_stt_pipeline(
            preprocessed_wav=input_path,
            work_dir=work_dir,
            use_local_whisper=True,
            model_size=model,
            device=device
        )

        # 결과를 지정된 출력 파일로 복사
        import shutil
        shutil.copy(result_path, output_path)

        click.echo(f"✅ Transcript saved to {output_path}")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--input', '-i', required=True, type=click.Path(exists=True), help='입력 오디오 파일 (WAV)')
@click.option('--output', '-o', required=True, type=click.Path(), help='출력 JSON 파일')
@click.option('--model', '-m', default='senko', type=click.Choice(['senko', 'nemo']), help='화자 분리 모델')
@click.option('--device', '-d', default='cpu', help='디바이스 (cpu/cuda)')
def diarize(input, output, model, device):
    """화자 분리 - 오디오에서 화자별 구간 감지"""
    click.echo(f"🎤 Diarization 시작: {input}")
    click.echo(f"모델: {model}, 디바이스: {device}")

    try:
        result = run_diarization(
            audio_path=Path(input),
            device=device,
            mode=model
        )

        # JSON 저장
        output_path = Path(output)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        click.echo(f"✅ 화자 수: {len(result['embeddings'])}명")
        click.echo(f"✅ 세그먼트 수: {len(result['turns'])}개")
        click.echo(f"✅ Diarization result saved to {output_path}")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--text', '-t', required=True, type=click.Path(exists=True), help='입력 텍스트 파일')
@click.option('--output', '-o', required=True, type=click.Path(), help='출력 JSON 파일')
@click.option('--min-score', default=7, type=int, help='최소 중요도 (1-10, 기본값: 7)')
def keywords(text, output, min_score):
    """키워드 추출 - 전문용어 자동 추출"""
    click.echo(f"🔑 키워드 추출 시작: {text}")

    try:
        # 텍스트 읽기
        with open(text, 'r', encoding='utf-8') as f:
            content = f.read()

        # 키워드 추출 (async 함수 실행)
        result = asyncio.run(run_keyword_extraction_agent(content))

        # 최소 점수 필터링
        filtered = [kw for kw in result if kw.get('importance', 0) >= min_score]

        # JSON 저장
        output_path = Path(output)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(filtered, f, ensure_ascii=False, indent=2)

        click.echo(f"✅ 추출된 키워드: {len(result)}개 (필터링 후: {len(filtered)}개)")
        click.echo(f"✅ Keywords saved to {output_path}")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--text', '-t', required=True, type=click.Path(exists=True), help='입력 텍스트 파일')
@click.option('--output', '-o', required=True, type=click.Path(), help='출력 JSON 파일')
@click.option('--date', '-d', default=None, help='회의 날짜 (YYYY-MM-DD, 기본값: 오늘)')
def todo(text, output, date):
    """TODO 추출 - 실행 가능한 할 일 자동 파싱"""
    click.echo(f"✅ TODO 추출 시작: {text}")

    try:
        # 텍스트 읽기
        with open(text, 'r', encoding='utf-8') as f:
            content = f.read()

        # TODO 추출
        if date is None:
            from datetime import datetime
            date = datetime.now().strftime("%Y-%m-%d")

        result = extract_todos_from_transcript(
            transcript_text=content,
            meeting_date=date,
            openai_api_key=settings.OPENAI_API_KEY
        )

        # JSON 저장
        output_path = Path(output)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({"todos": result}, f, ensure_ascii=False, indent=2)

        click.echo(f"✅ 추출된 TODO: {len(result)}개")
        click.echo(f"✅ TODOs saved to {output_path}")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--transcript', '-t', required=True, type=click.Path(exists=True), help='입력 JSON 파일 (세그먼트)')
@click.option('--output', '-o', required=True, type=click.Path(), help='출력 JSON 파일')
@click.option('--type', '-T', default='d', help='회의 유형 (a-f 또는 전체 이름)')
@click.option('--mode', '-m', default='section', type=click.Choice(['single', 'section']), help='분석 모드')
def template(transcript, output, type, mode):
    """템플릿 피팅 - 회의록 구조화"""
    click.echo(f"📋 템플릿 피팅 시작: {transcript}")
    click.echo(f"회의 유형: {type}, 모드: {mode}")

    try:
        # JSON 읽기
        with open(transcript, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 세그먼트 및 화자 매핑 추출
        if isinstance(data, list):
            segments = data
            speaker_mapping = {}
        elif isinstance(data, dict):
            segments = data.get('segments', data.get('transcript_segments', []))
            speaker_mapping = data.get('speaker_mapping', {})
        else:
            raise ValueError("Invalid JSON format")

        # 템플릿 피팅 실행
        result = asyncio.run(run_template_fitting_agent(
            transcript_segments=segments,
            speaker_mapping=speaker_mapping,
            meeting_type=type
        ))

        # JSON 저장
        output_path = Path(output)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        click.echo(f"✅ 섹션 수: {len(result.get('sections', []))}개")
        click.echo(f"✅ Structured meeting saved to {output_path}")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--input', '-i', required=True, type=click.Path(exists=True), help='입력 오디오 파일')
@click.option('--participants', '-p', required=True, help='참여자 이름 (쉼표로 구분)')
@click.option('--meeting-type', '-t', default='d', help='회의 유형 (a-f)')
@click.option('--output-dir', '-o', default='./results', type=click.Path(), help='출력 디렉토리')
def pipeline(input, participants, meeting_type, output_dir):
    """전체 파이프라인 - 오디오부터 회의록까지 한 번에 실행"""
    click.echo(f"🚀 전체 파이프라인 시작: {input}")
    click.echo(f"참여자: {participants}")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    input_path = Path(input)
    base_name = input_path.stem

    try:
        # 1. STT
        click.echo("\n[1/6] STT 실행 중...")
        work_dir = output_path / f"{base_name}_work"
        work_dir.mkdir(exist_ok=True)

        transcript_path = run_stt_pipeline(
            preprocessed_wav=input_path,
            work_dir=work_dir,
            use_local_whisper=True,
            model_size='large-v3',
            device='cpu'
        )
        click.echo(f"✅ STT 완료: {transcript_path}")

        # 2. Diarization
        click.echo("\n[2/6] 화자 분리 실행 중...")
        diarization_result = run_diarization(
            audio_path=input_path,
            device='cpu',
            mode='senko'
        )
        diarization_path = output_path / f"{base_name}_diarization.json"
        with open(diarization_path, 'w', encoding='utf-8') as f:
            json.dump(diarization_result, f, ensure_ascii=False, indent=2)
        click.echo(f"✅ 화자 분리 완료: {len(diarization_result['embeddings'])}명")

        # 3. 키워드 추출
        click.echo("\n[3/6] 키워드 추출 실행 중...")
        with open(transcript_path, 'r', encoding='utf-8') as f:
            transcript_text = f.read()

        keywords_result = asyncio.run(run_keyword_extraction_agent(transcript_text))
        keywords_path = output_path / f"{base_name}_keywords.json"
        with open(keywords_path, 'w', encoding='utf-8') as f:
            json.dump(keywords_result, f, ensure_ascii=False, indent=2)
        click.echo(f"✅ 키워드 추출 완료: {len(keywords_result)}개")

        # 4. TODO 추출
        click.echo("\n[4/6] TODO 추출 실행 중...")
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        todos_result = extract_todos_from_transcript(transcript_text, today)
        todos_path = output_path / f"{base_name}_todos.json"
        with open(todos_path, 'w', encoding='utf-8') as f:
            json.dump({"todos": todos_result}, f, ensure_ascii=False, indent=2)
        click.echo(f"✅ TODO 추출 완료: {len(todos_result)}개")

        # 5. 최종 결과 요약
        click.echo("\n" + "="*50)
        click.echo("✅ 전체 파이프라인 완료!")
        click.echo("="*50)
        click.echo(f"📁 출력 디렉토리: {output_path}")
        click.echo(f"  - 전사본: {transcript_path.name}")
        click.echo(f"  - 화자 분리: {diarization_path.name}")
        click.echo(f"  - 키워드: {keywords_path.name}")
        click.echo(f"  - TODO: {todos_path.name}")

    except Exception as e:
        click.echo(f"\n❌ Error: {e}", err=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    cli()
