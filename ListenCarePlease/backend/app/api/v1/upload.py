from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import os
import uuid
from datetime import datetime
from app.schemas.audio import AudioFileUploadResponse, AudioFileStatusResponse

router = APIRouter()

# 임시 저장소 (실제로는 DB 사용)
UPLOADED_FILES = {}


@router.post("/upload", response_model=AudioFileUploadResponse)
async def upload_audio_file(file: UploadFile = File(...)):
    """
    오디오 파일 업로드
    로그인 없이 임시로 파일을 저장합니다.
    """
    # 파일 확장자 검증
    allowed_extensions = [".mp3", ".m4a", ".wav", ".ogg", ".flac"]
    file_ext = os.path.splitext(file.filename)[1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다. 허용된 형식: {', '.join(allowed_extensions)}"
        )

    # 파일 크기 제한 (100MB)
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    file_content = await file.read()

    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail="파일 크기는 100MB를 초과할 수 없습니다."
        )

    # 고유 파일 ID 생성
    file_id = str(uuid.uuid4())

    # 파일 저장 경로
    upload_dir = "/app/uploads"
    os.makedirs(upload_dir, exist_ok=True)

    safe_filename = f"{file_id}{file_ext}"
    file_path = os.path.join(upload_dir, safe_filename)

    # 파일 저장
    with open(file_path, "wb") as f:
        f.write(file_content)

    # 임시 저장소에 메타데이터 저장
    UPLOADED_FILES[file_id] = {
        "file_id": file_id,
        "filename": file.filename,
        "file_path": file_path,
        "file_size": len(file_content),
        "status": "uploaded",
        "created_at": datetime.now()
    }

    return AudioFileUploadResponse(
        file_id=file_id,
        filename=file.filename,
        message="파일 업로드가 완료되었습니다."
    )


@router.get("/files/{file_id}", response_model=AudioFileStatusResponse)
async def get_file_status(file_id: str):
    """
    파일 상태 조회
    """
    if file_id not in UPLOADED_FILES:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    file_info = UPLOADED_FILES[file_id]

    return AudioFileStatusResponse(
        file_id=file_info["file_id"],
        filename=file_info["filename"],
        status=file_info["status"],
        duration=file_info.get("duration"),
        created_at=file_info["created_at"]
    )


@router.delete("/files/{file_id}")
async def delete_file(file_id: str):
    """
    파일 삭제
    """
    if file_id not in UPLOADED_FILES:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    file_info = UPLOADED_FILES[file_id]

    # 실제 파일 삭제
    if os.path.exists(file_info["file_path"]):
        os.remove(file_info["file_path"])

    # 메모리에서 삭제
    del UPLOADED_FILES[file_id]

    return {"message": "파일이 삭제되었습니다."}
