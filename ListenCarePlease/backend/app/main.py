import app.patch_torch  # Apply monkey patch first
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 앱 시작 시 LangSmith 설정
@app.on_event("startup")
async def startup_event():
    """앱 시작 시 실행되는 이벤트"""
    import os

    # LangSmith 추적 환경 변수 확인 및 자동 조정
    langchain_tracing = os.getenv("LANGCHAIN_TRACING_V2", "false")
    # LANGSMITH_API_KEY도 확인 (일부 설정에서 사용)
    langchain_api_key = os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY")
    langchain_project = os.getenv("LANGCHAIN_PROJECT", "speaker-tagging-agent")

    if langchain_tracing.lower() == "true":
        if langchain_api_key and langchain_api_key.strip():
            # LANGCHAIN_API_KEY가 없으면 LANGSMITH_API_KEY를 복사
            if not os.getenv("LANGCHAIN_API_KEY") and os.getenv("LANGSMITH_API_KEY"):
                os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY")
            print(f"✅ LangSmith 추적 활성화됨 (프로젝트: {langchain_project})")
        else:
            # API 키가 없으면 자동으로 추적 비활성화 (에러 방지)
            os.environ["LANGCHAIN_TRACING_V2"] = "false"
            print("⚠️ LANGCHAIN_TRACING_V2=true이지만 LANGCHAIN_API_KEY 또는 LANGSMITH_API_KEY가 없어서 추적을 비활성화했습니다.")
            print("   LangSmith 추적을 사용하려면 .env 파일에 LANGCHAIN_API_KEY를 설정하세요.")
    else:
        print("ℹ️ LangSmith 추적이 비활성화되어 있습니다. (LANGCHAIN_TRACING_V2=true로 설정하세요)")

    print("✅ Application startup complete")


@app.get("/")
async def root():
    return {
        "message": "Welcome to ListenCarePlease API",
        "version": settings.VERSION,
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# API 라우터 추가
from app.api.v1 import auth, oauth, upload, tagging, processing, dashboard, rag, todo, efficiency
app.include_router(auth.router, prefix=settings.API_V1_STR, tags=["auth"])
app.include_router(oauth.router, prefix=settings.API_V1_STR, tags=["oauth"])
app.include_router(upload.router, prefix=settings.API_V1_STR, tags=["upload"])
app.include_router(tagging.router, prefix=f"{settings.API_V1_STR}/tagging", tags=["tagging"])
app.include_router(processing.router, prefix=settings.API_V1_STR, tags=["processing"])
app.include_router(dashboard.router, prefix=f"{settings.API_V1_STR}/dashboard", tags=["dashboard"])
app.include_router(rag.router, prefix=f"{settings.API_V1_STR}/rag", tags=["rag"])
app.include_router(todo.router, prefix=f"{settings.API_V1_STR}", tags=["todo"])
app.include_router(efficiency.router, prefix=f"{settings.API_V1_STR}/efficiency", tags=["efficiency"])

from app.api.v1 import template
app.include_router(template.router, prefix=f"{settings.API_V1_STR}/template", tags=["template"])

from app.api.v1 import keyword
app.include_router(keyword.router, prefix=f"{settings.API_V1_STR}/keyword", tags=["keyword"])

from app.api.v1 import speaker_profile
app.include_router(speaker_profile.router, prefix=f"{settings.API_V1_STR}/speaker-profiles", tags=["speaker-profiles"])

from app.api.v1 import export
app.include_router(export.router, prefix=f"{settings.API_V1_STR}/export", tags=["export"])

from app.api.v1 import calendar
app.include_router(calendar.router, prefix=f"{settings.API_V1_STR}/calendar", tags=["calendar"])
