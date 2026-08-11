from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables / .env file.

    REQUIRED secrets (no default — app refuses to start if unset):
        POSTGRES_PASS, API_SECRET_KEY

    Recommended to set (app warns loudly if missing):
        REDIS_PASSWORD, GROQ_API_KEY, JINA_API_KEY
    """

    # ── PostgreSQL ────────────────────────────────────────────────────────
    postgres_user: str = "postgres"
    postgres_pass: str = "1234"  # REQUIRED — no default intentionally
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = ""

    # ── JWT Auth ──────────────────────────────────────────────────────────
    api_secret_key: str  # REQUIRED — no default intentionally

    # ── External APIs ─────────────────────────────────────────────────────
    hf_api: str = ""
    groq_api_key: str = ""
    jina_api_key: str = ""
    remote_embed_url: str = ""

    # ── General Settings ──────────────────────────────────────────────────
    debug: bool = False

    # ── Internal service-to-service auth (Celery → FastAPI metrics) ───────
    internal_metrics_api_key: str = ""

    # ── Redis ─────────────────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = (
        "atlas_redis_password"  # Empty = no auth; set a real password in prod
    )
    redis_db: int = 0
    stm_ttl_seconds: int = 7200
    stm_max_turns: int = 20

    # ── RAG pipeline timeouts ─────────────────────────────────────────────
    semantic_chunking_timeout: int = 900
    embedding_request_timeout: float = 120.0

    # ── Qdrant ────────────────────────────────────────────────────────────
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "atlas_documents1"
    semantic_memory_collection: str = "atlas_semantic_memory"
    semantic_memory_top_k: int = 5
    episodic_memory_ttl_days: int = 90
    episodic_memory_recent_limit: int = 3
    semantic_memory_prune_importance_below: float = 0.15
    llm_context_window_tokens: int = 8000
    sparse_embedding_model: str = "Qdrant/bm25"
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"

    # ── SMTP / Email ──────────────────────────────────────────────────────
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    frontend_url: str = "http://localhost:3000"

    class Config:
        env_file = ".env"
        extra = "ignore"

    # ── Startup validation ────────────────────────────────────────────────
    @model_validator(mode="after")
    def _check_required_secrets(self) -> "Settings":
        """
        Fail fast at import time if required secrets are missing.
        This prevents accidentally running production with empty/default credentials.
        """
        missing = []
        if not self.postgres_pass:
            missing.append("POSTGRES_PASS")
        if not self.api_secret_key:
            missing.append("API_SECRET_KEY")
        if missing:
            raise ValueError(
                f"Required environment variable(s) not set: {', '.join(missing)}. "
                "Set them in your .env file or system environment before starting the server."
            )
        return self

    # ── Computed connection strings ───────────────────────────────────────
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_pass}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def REDIS_URL(self) -> str:
        """Redis URL with optional authentication."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def REDIS_URL_NO_DB(self) -> str:
        """Redis URL without database number (for semantic cache)."""
        if self.redis_password:
            return (
                f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/0"
            )
        return f"redis://{self.redis_host}:{self.redis_port}/0"


settings = Settings()
