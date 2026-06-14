"""Application configuration loaded from environment variables / .env files.

All settings are centralized here so the rest of the codebase never reads
``os.environ`` directly. Provider credentials (OpenAI, Anthropic) are declared
now but only consumed in later phases.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings.

    Values are resolved, in order of precedence, from real environment
    variables and then from a local ``.env`` file. Unknown keys are ignored so
    a shared ``.env`` can hold variables for several services.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application -----------------------------------------------------
    app_name: str = "RAG"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = True

    # CORS origins allowed to call the API directly (the dev/prod frontends
    # talk to the backend through a same-origin proxy, so this is mostly a
    # safety net for direct access).
    cors_origins: list[str] = ["http://localhost:5173"]

    # --- PostgreSQL ------------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "rag"
    postgres_password: str = "rag"
    postgres_db: str = "rag"

    # --- Qdrant ----------------------------------------------------------
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    # --- Redis -----------------------------------------------------------
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # --- Providers (consumed in later phases) ----------------------------
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    @property
    def postgres_dsn(self) -> str:
        """Async SQLAlchemy DSN (asyncpg driver)."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance (read once per process)."""
    return Settings()


settings = get_settings()
