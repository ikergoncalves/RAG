"""Application configuration loaded from environment variables / .env files.

All settings are centralized here so the rest of the codebase never reads
``os.environ`` directly. Provider credentials (OpenAI, Anthropic) are declared
now but only consumed in later phases.
"""

# Temporary startup diagnostics: markers around the imports and around the
# Settings() instantiation, to isolate a startup hang (is it importing
# pydantic_settings, or reading/validating an env var?). The top marker precedes
# all imports, so E402 is silenced file-wide for now. Remove once resolved.
# ruff: noqa: E402

print("[startup] config: begin imports", flush=True)

from functools import lru_cache
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict

print("[startup] config: imports done (pydantic_settings loaded)", flush=True)


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
    # API key for authenticated Qdrant deployments (e.g. Qdrant Cloud). The
    # local Qdrant in docker-compose requires no auth, so this stays unset
    # (``None``) there; the client passes no key when it is empty.
    qdrant_api_key: str | None = None
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

    # --- Retrieval / re-ranking ------------------------------------------
    # Re-ranking is delegated to Cohere's hosted Rerank API rather than a local
    # cross-encoder, so the backend image ships no torch / sentence-transformers
    # and stays small enough for memory-constrained hosts (e.g. free deploy
    # tiers). When ``cohere_api_key`` is unset, re-ranking degrades gracefully to
    # a no-op that returns the fused candidates in their original order (see
    # ``app/services/retrieval/cohere_reranker.py``).
    cohere_api_key: str | None = None
    cohere_rerank_model: str = "rerank-v3.5"
    # Candidates pulled by each prefetch branch (dense, sparse) before RRF fusion.
    retrieval_prefetch_limit: int = 20
    # Number of fused candidates handed to the reranker for re-ranking.
    retrieval_candidates: int = 20
    # Default number of chunks returned after re-ranking.
    retrieval_top_k: int = 5

    # --- Generation (Claude) ---------------------------------------------
    # Model used to stream the cited answer from the retrieved context.
    generation_model: str = "claude-sonnet-4-6"
    # Smaller/cheaper model used for the (non-streaming) tool-use call that
    # extracts verbatim citation quotes from the generated answer.
    citation_extraction_model: str = "claude-haiku-4-5-20251001"

    # --- Redis -----------------------------------------------------------
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    # Auth for managed Redis (e.g. Railway). The local docker-compose Redis needs
    # no auth, so these stay unset there. When a password is set, the connection
    # URL also carries the ACL username (Redis defaults to "default").
    redis_user: str | None = None
    redis_password: str | None = None

    # --- Cache (Redis) ---------------------------------------------------
    # TTL for cached query embeddings (dense vectors keyed by the normalized
    # query hash). Embeddings are deterministic for a given model, so a long
    # TTL is safe; reindexing documents does not change a query's embedding.
    cache_embedding_ttl_seconds: int = 86_400
    # TTL for cached full responses ({answer, citations}) keyed by the same
    # query hash. Kept short so newly ingested documents are reflected quickly.
    cache_response_ttl_seconds: int = 3_600

    # --- Cost estimation (USD per 1k tokens) -----------------------------
    # Defaults match the configured providers: ``claude-sonnet-4-6`` for
    # generation ($3 / $15 per 1M input/output tokens) and OpenAI
    # ``text-embedding-3-small`` ($0.02 per 1M tokens). Override these if the
    # generation/embedding models change so cost tracking stays accurate.
    llm_cost_prompt_per_1k_tokens: float = 0.003
    llm_cost_completion_per_1k_tokens: float = 0.015
    embedding_cost_per_1k_tokens: float = 0.00002

    # --- Observability (Langfuse) ----------------------------------------
    # LLM tracing. When the keys are unset the instrumentation is a silent
    # no-op, so the system runs identically with or without Langfuse.
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "http://localhost:3000"

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
        """Redis connection URL, including credentials when a password is set.

        Local development Redis needs no auth, so the bare host/port form is used
        when no password is configured. Managed Redis (e.g. Railway) requires a
        password plus an ACL username (``default`` unless overridden); both are
        URL-encoded so special characters in the password don't break the URL.
        """
        if self.redis_password:
            user = quote(self.redis_user or "default", safe="")
            password = quote(self.redis_password, safe="")
            return (
                f"redis://{user}:{password}@"
                f"{self.redis_host}:{self.redis_port}/{self.redis_db}"
            )
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def qdrant_url(self) -> str:
        """REST URL for Qdrant.

        Uses HTTPS when an API key is configured (managed Qdrant such as Qdrant
        Cloud requires TLS) and plain HTTP otherwise (the local docker-compose
        Qdrant, which needs no key).
        """
        scheme = "https" if self.qdrant_api_key else "http"
        return f"{scheme}://{self.qdrant_host}:{self.qdrant_port}"


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance (read once per process)."""
    return Settings()


print("[startup] config: instantiating Settings()...", flush=True)
settings = get_settings()
print("[startup] config: Settings() instantiated", flush=True)
