"""Application settings: repo-root .env (not committed), see .env.example."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-root .env (the package lives at prototype/backend/src/lineagelite/, so four levels up;
# matches the AGENTS.md configuration convention)
ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    secret_key: str = "dev-secret-change-me"
    jwt_expire_hours: int = 24
    data_dir: str = "./data"
    admin_username: str = "admin"
    admin_password: str = "admin123"
    max_upload_mb: int = 50  # Per-file upload size limit (MB)
    # Allowed cross-origin frontend origins (comma-separated); default is only the local Vite dev server
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # M4: OpenAI-compatible LLM (injected from the repo-root .env; empty means not configured, /ai/chat returns 503).
    # The API key may be empty, which makes local OpenAI-compatible services without auth easy to use.
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    # M5: embeddings (semantic lineage suggestions). OpenAI / Alibaba Cloud DashScope compatible
    # mode both work, switched by the base_url of LangChain OpenAIEmbeddings; empty by default
    # means the semantic layer degrades to pure heuristics.
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""


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
