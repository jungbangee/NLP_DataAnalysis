"""
TODO API 엔드포인트
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from app.db.base import get_db
from app.models.audio_file import AudioFile
from app.models.todo import TodoItem, TodoPriority
from app.models.transcript import FinalTranscript
from app.services.todo_extractor import extract_todos_from_transcript

router = APIRouter()

# ===== Pydantic Schemas =====

class TodoItemResponse(BaseModel):
    """TODO 아이템 응답"""
    id: int
    file_id: int
    task: str
    assignee: Optional[str]
    due_date: Optional[datetime]
    priority: TodoPriority
    created_at: datetime

    class Config:
        from_attributes = True

class TodoListResponse(BaseModel):
    """TODO 리스트 응답"""
    file_id: int
    original_filename: str
    meeting_date: Optional[str]
    todos: List[TodoItemResponse]

class TodoExtractRequest(BaseModel):
    """TODO 추출 요청"""
    meeting_date: Optional[str] = None  # YYYY-MM-DD, None이면 파일 생성일 사용

# ===== API Endpoints =====

@router.post("/todos/extract/{file_id}", response_model=TodoListResponse)
async def extract_and_save_todos(
    file_id: int,
    request: TodoExtractRequest,
    db: Session = Depends(get_db)
):
    """
    회의록에서 TODO 추출 및 저장

    - 날짜/요일 키워드가 포함된 문장 + 앞뒤 3문장씩 추출
    - GPT-4o로 TODO 생성
    - 데이터베이스에 저장
    """
    # 1. 파일 존재 확인
    audio_file = db.query(AudioFile).filter(AudioFile.id == file_id).first()
    if not audio_file:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    # 2. 회의록 텍스트 가져오기 (여러 세그먼트를 하나로 합침)
    final_transcripts = db.query(FinalTranscript).filter(
        FinalTranscript.audio_file_id == file_id
    ).order_by(FinalTranscript.segment_index).all()

    if not final_transcripts:
        raise HTTPException(status_code=404, detail="회의록이 아직 생성되지 않았습니다.")

    # 3. 회의록 텍스트 결합
    transcript_text = ' '.join([segment.text for segment in final_transcripts])

    # 4. 회의 날짜 결정
    meeting_date = request.meeting_date
    if not meeting_date:
        # 파일 생성일을 회의 날짜로 사용
        meeting_date = audio_file.created_at.strftime("%Y-%m-%d")

    # 5. TODO 추출
    try:
        todos_data = extract_todos_from_transcript(
            transcript_text=transcript_text,
            meeting_date=meeting_date
        )
    except Exception as e:
        import traceback
        error_detail = f"TODO 추출 중 오류: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)  # 로그 출력
        raise HTTPException(
            status_code=500,
            detail=f"TODO 추출 중 오류가 발생했습니다: {str(e)}"
        )

    # 6. 기존 TODO 삭제 (재추출 시)
    db.query(TodoItem).filter(TodoItem.file_id == file_id).delete()

    # 7. 새로운 TODO 저장
    todo_items = []
    for todo_data in todos_data:
        # due_date 파싱
        due_date = None
        if todo_data.get('due_date'):
            try:
                due_date = datetime.strptime(todo_data['due_date'], "%Y-%m-%d %H:%M")
            except ValueError:
                pass

        todo_item = TodoItem(
            file_id=file_id,
            task=todo_data['task'],
            assignee=todo_data.get('assignee'),
            due_date=due_date,
            priority=TodoPriority(todo_data.get('priority', 'Medium')),
            created_at=datetime.now()
        )
        db.add(todo_item)
        todo_items.append(todo_item)

    db.commit()

    # 8. 저장된 TODO 조회
    for item in todo_items:
        db.refresh(item)

    return TodoListResponse(
        file_id=file_id,
        original_filename=audio_file.original_filename,
        meeting_date=meeting_date,
        todos=[
            TodoItemResponse.from_orm(item) for item in todo_items
        ]
    )

@router.get("/todos/{file_id}", response_model=TodoListResponse)
async def get_todos(file_id: int, db: Session = Depends(get_db)):
    """
    파일의 TODO 리스트 조회
    """
    # 파일 존재 확인
    audio_file = db.query(AudioFile).filter(AudioFile.id == file_id).first()
    if not audio_file:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    # TODO 조회
    todos = db.query(TodoItem).filter(
        TodoItem.file_id == file_id
    ).order_by(TodoItem.due_date.asc()).all()

    # 회의 날짜 (파일 생성일)
    meeting_date = audio_file.created_at.strftime("%Y-%m-%d")

    return TodoListResponse(
        file_id=file_id,
        original_filename=audio_file.original_filename,
        meeting_date=meeting_date,
        todos=[
            TodoItemResponse.from_orm(item) for item in todos
        ]
    )

@router.delete("/todos/{file_id}")
async def delete_all_todos(file_id: int, db: Session = Depends(get_db)):
    """
    파일의 모든 TODO 삭제
    """
    # 파일 존재 확인
    audio_file = db.query(AudioFile).filter(AudioFile.id == file_id).first()
    if not audio_file:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    # TODO 삭제
    deleted_count = db.query(TodoItem).filter(TodoItem.file_id == file_id).delete()
    db.commit()

    return {
        "message": f"{deleted_count}개의 TODO가 삭제되었습니다.",
        "file_id": file_id
    }

@router.delete("/todos/{file_id}/{todo_id}")
async def delete_todo(file_id: int, todo_id: int, db: Session = Depends(get_db)):
    """
    특정 TODO 삭제
    """
    todo = db.query(TodoItem).filter(
        TodoItem.id == todo_id,
        TodoItem.file_id == file_id
    ).first()

    if not todo:
        raise HTTPException(status_code=404, detail="TODO를 찾을 수 없습니다.")

    db.delete(todo)
    db.commit()

    return {
        "message": "TODO가 삭제되었습니다.",
        "todo_id": todo_id
    }
