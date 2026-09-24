from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    session_secret: str = "development-only-change-me"
    database_url: str = "sqlite:///./analyst.db"
    data_dir: Path = Path("./data")
    max_upload_bytes: int = 25_000_000
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/callback"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
