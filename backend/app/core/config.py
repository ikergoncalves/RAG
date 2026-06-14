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
    # Collection holding chunk vectors (dense + sparse/BM25 for hybrid search).
    qdrant_collection: str = "chunks"

    # --- Embeddings / indexing -------------------------------------------
    # Dense embeddings (OpenAI). ``text-embedding-3-small`` is 1536-dimensional.
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    # Number of chunks embedded per OpenAI request.
    embedding_batch_size: int = 100
    # Retries on transient OpenAI errors (rate limits, timeouts) before giving up.
    embedding_max_retries: int = 5
    # FastEmbed model used to produce sparse (BM25) vectors for hybrid search.
    sparse_embedding_model: str = "Qdrant/bm25"

    # --- Redis -----------------------------------------------------------
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # --- Ingestion / chunking --------------------------------------------
    # Directory where uploaded source files are stored.
    upload_dir: str = "var/uploads"
    # Token-based chunking parameters (see app/services/chunking.py).
    tiktoken_encoding: str = "cl100k_base"
    chunk_size_tokens: int = 400
    chunk_overlap_tokens: int = 50

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
