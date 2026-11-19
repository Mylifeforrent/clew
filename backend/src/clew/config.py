"""Application configuration: repository-root .env (untracked), see .env.example."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository-root .env (the package lives at backend/src/clew/, so up 3 levels;
# matches the AGENTS.md configuration convention)
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    secret_key: str = "dev-secret-change-me"
    jwt_expire_hours: int = 24
    data_dir: str = "./data"
    admin_username: str = "admin"
    admin_password: str = "admin123"
    max_upload_mb: int = 50  # per-file upload size limit (MB)
    # Allowed CORS origins for the frontend (comma-separated); defaults to the
    # local Vite dev server only
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # M4: OpenAI-compatible LLM (injected from the repository-root .env; an empty
    # default means not configured, and /ai/chat returns 503).
    # The API key may be empty, to support local OpenAI-compatible services that
    # require no authentication.
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    # M5: embeddings (semantic lineage suggestions). Works with OpenAI / Alibaba
    # DashScope compatible mode, switched via LangChain OpenAIEmbeddings base_url;
    # empty default = the semantic layer degrades to pure heuristics.
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    # Doc 08 R10: conversation context token budget (rough estimate; over budget
    # trims the oldest rounds as a whole block)
    llm_context_token_budget: int = 96_000


def get_settings() -> Settings:
    return Settings()


def db_path(settings: Settings | None = None) -> Path:
    s = settings or get_settings()
    return Path(s.data_dir) / "lineage.db"


def files_dir(settings: Settings | None = None) -> Path:
    s = settings or get_settings()
    return Path(s.data_dir) / "files"


def resolve_storage(rel_path: str) -> Path:
    """Resolve source_file.storage_path (relative to data_dir) to an absolute path."""
    return Path(get_settings().data_dir) / rel_path
