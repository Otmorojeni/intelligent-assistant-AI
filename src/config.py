from pathlib import Path
import secrets
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Paths
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
    MATERIALS_DIR: Path = PROJECT_ROOT / "materials"
    GENERATED_DOCS_DIR: Path = PROJECT_ROOT / "generated_docs"
    STATIC_DIR: Path = PROJECT_ROOT / "ui"

    # Database
    POSTGRES_HOST: str = "127.0.0.1"
    POSTGRES_PORT: int = 5433
    POSTGRES_DB: str = "cdo_assistant"
    POSTGRES_USER: str = "cdo_admin"
    POSTGRES_PASSWORD: str = ""
    DATABASE_URL: str = ""
    DATABASE_URL_SYNC: str = ""

    # Local LLM (Ollama) — tuned for MSKs-2 VM (2 vCPU, 4 GB RAM)
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_MODEL: str = "qwen2.5:1.5b"
    OLLAMA_FALLBACK_MODEL: str = "qwen2.5:1.5b"
    LLM_TEMPERATURE: float = 0.0
    LLM_TIMEOUT_SECONDS: float = 45.0
    LLM_NUM_CTX: int = 2048
    LLM_NUM_PREDICT: int = 450
    LLM_NUM_THREAD: int = 2
    LLM_KEEP_ALIVE: str = "24h"

    # Application & Server
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Security & RBAC
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    ADMIN_DEMO_PASSWORD: str = "cdo-admin-2026"

    # RAG parameters
    MIN_RELEVANCE_THRESHOLD: float = 25.0
    TOP_K_CHUNKS: int = 5

    @model_validator(mode="after")
    def assemble_db_urls(self) -> "Settings":
        if not self.SECRET_KEY:
            self.SECRET_KEY = secrets.token_urlsafe(32)
        if not self.DATABASE_URL and self.POSTGRES_PASSWORD:
            self.DATABASE_URL = (
                f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
                f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        if not self.DATABASE_URL_SYNC and self.POSTGRES_PASSWORD:
            self.DATABASE_URL_SYNC = (
                f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
                f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        return self

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
settings.GENERATED_DOCS_DIR.mkdir(parents=True, exist_ok=True)
