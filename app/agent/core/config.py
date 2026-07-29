"""Agent-specific configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class AgentSettings(BaseSettings):
    max_steps_per_subquestion: int = 6
    max_subquestions: int = 10
    max_total_steps: int = 50
    agent_timeout_seconds: float = 120.0
    sql_query_timeout_seconds: float = 30.0
    sql_max_rows: int = 1000
    sql_max_result_rows_in_prompt: int = 20
    sql_max_allowed_cost: float = 1000.0
    sql_cost_unknown_default: float = 1001.0  # fail-closed when EXPLAIN fails
    sql_namespace: str = ""  # comma-separated allowed tables; empty = all reflected tables
    sql_allowed_columns: str = ""  # comma-separated col allowlist; empty = no column restriction
    schema_cache_ttl_seconds: int = 300
    retrieval_cache_ttl_seconds: int = 300
    retrieval_top_k: int = 5
    retrieval_doc_preview_chars: int = 300
    llm_retry_attempts: int = 3
    llm_retry_min_wait_seconds: float = 0.5
    llm_retry_max_wait_seconds: float = 4.0

    class Config:
        env_file = ".env"
        env_prefix = "AGENT_"
        extra = "ignore"

    @property
    def allowed_tables(self) -> set[str] | None:
        if not self.sql_namespace.strip():
            return None
        return {t.strip() for t in self.sql_namespace.split(",") if t.strip()}

    @property
    def allowed_columns(self) -> set[str] | None:
        if not self.sql_allowed_columns.strip():
            return None
        return {c.strip() for c in self.sql_allowed_columns.split(",") if c.strip()}


agent_settings = AgentSettings()
