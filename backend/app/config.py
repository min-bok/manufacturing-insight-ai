from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import os

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]
if load_dotenv:
    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(BACKEND_DIR / ".env.local")
    load_dotenv(ROOT_DIR / ".env")


def _resolve_project_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (ROOT_DIR / path).resolve()


def _env_value(key: str, default: str = "") -> str:
    value = os.getenv(key, default).strip()
    duplicated_prefix = f"{key}="
    if value.startswith(duplicated_prefix):
        return value[len(duplicated_prefix) :].strip()
    return value


class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    dataset_path: Path = _resolve_project_path(os.getenv("DATASET_PATH", "data/manufacturing_data.csv"))
    database_path: Path = _resolve_project_path(os.getenv("DATABASE_PATH", ".runtime/app.db"))
    gemini_api_key: str = _env_value("GEMINI_API_KEY")
    gemini_model: str = _env_value("GEMINI_MODEL", "gemini-3.5-flash")
    gemini_timeout_seconds: int = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "60"))
    llm_daily_user_limit: int = int(os.getenv("LLM_DAILY_USER_LIMIT", "5"))
    llm_daily_global_limit: int = int(os.getenv("LLM_DAILY_GLOBAL_LIMIT", "100"))
    llm_max_output_tokens: int = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "900"))
    cors_origins: list[str] = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    ]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
