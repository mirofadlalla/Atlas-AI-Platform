"""Agent-specific configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AGENT_",
        extra="ignore",
    )

    max_steps_per_subquestion: int = 6
    max_subquestions: int = 10
    max_total_steps: int = 50
    agent_timeout_seconds: float = 120.0
    sql_query_timeout_seconds: float = 30.0
    sql_max_rows: int = 1000
    sql_max_result_rows_in_prompt: int = 20
    sql_max_allowed_cost: float = 1000.0
    sql_cost_unknown_default: float = 1001.0
    sql_namespace: str = ""  # أسماء الجداول المسموح بيها (مبدئيًا فاضي).
    sql_allowed_columns: str = ""  # أسماء الأعمدة المسموح بيها (مبدئيًا فاضي).
    schema_cache_ttl_seconds: int = (
        300  # مدة صلاحية الكاش بالثواني (هنا 300 ثانية = 5 دقائق).
    )
    retrieval_cache_ttl_seconds: int = (
        300  # مدة صلاحية الكاش بالثواني (هنا 300 ثانية = 5 دقائق).
    )
    retrieval_top_k: int = 5
    retrieval_doc_preview_chars: int = 300
    llm_retry_attempts: int = 3
    llm_retry_min_wait_seconds: float = 0.5
    llm_retry_max_wait_seconds: float = 4.0
    llm_timeout_seconds: float = 45.0
    llm_max_tokens: int = 2048
    llm_temperature: float = 1.0
    llm_system_prompt: str = "You are a helpful assistant."
    llm_routing_model: str = ""
    llm_generation_model: str = "llama-3.3-70b-versatile"
    llm_input_cost_per_million: float = 0.59
    llm_output_cost_per_million: float = 0.79
    prompt_max_tokens: int = 12000
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_seconds: float = 60.0
    run_idempotency_enabled: bool = True
    run_idempotency_ttl_seconds: int = 3600
    loop_detection_window: int = 6

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
