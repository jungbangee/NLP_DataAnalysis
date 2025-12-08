from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    PROJECT_NAME: str = "ListenCarePlease"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Database
    MYSQL_USER: str
    MYSQL_PASSWORD: str
    MYSQL_HOST: str = "mysql"
    MYSQL_PORT: int = 3306
    MYSQL_DB: str

    @property
    def DATABASE_URL(self) -> str:
        return f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}"

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # OAuth - Google
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: Optional[str] = None

    # OAuth - Kakao
    KAKAO_CLIENT_ID: Optional[str] = None
    KAKAO_CLIENT_SECRET: Optional[str] = None
    KAKAO_REDIRECT_URI: Optional[str] = None

    # OAuth - GitHub
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    GITHUB_REDIRECT_URI: Optional[str] = None

    # CORS
    BACKEND_CORS_ORIGINS: list = ["http://localhost:3000", "http://localhost:3001", "http://localhost:3002", "http://localhost:3003", "http://frontend:3000", "http://18.204.107.68:3000"]

    # OpenAI
    OPENAI_API_KEY: Optional[str] = None

    # Whisper Settings
    WHISPER_MODE: str = "local"  # "local" or "api"
    WHISPER_MODEL_SIZE: str = "large-v3"  # tiny, base, small, medium, large, large-v3
    WHISPER_DEVICE: str = "cpu"  # cpu or cuda

    # Diarization Settings
    DIARIZATION_MODE: str = "nemo"  # "senko" (fast) or "nemo" (accurate)

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
