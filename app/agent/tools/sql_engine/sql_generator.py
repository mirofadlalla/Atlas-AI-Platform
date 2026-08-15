"""SQL generation using structured LLM output."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.agent.core.config import agent_settings
from app.agent.prompts.registry import prompt_registry
from app.agent.tools.sql_engine.schema_provider import get_schema_description
from app.agent.utils.context_budget import truncate_to_token_budget
from app.agent.utils.llm import call_agent_llm
from app.agent.utils.parsing import extract_first_json_block
from app.agent.utils.retry import with_retry

logger = logging.getLogger(__name__)


class SQLQuery(BaseModel):
    sql: str = Field(description="PostgreSQL SELECT query only")


def generate_sql(question: str, tenant_id: str | None = None, schema: str | None = None) -> str:
    schema = schema if schema is not None else get_schema_description(tenant_id=tenant_id)
    schema = truncate_to_token_budget(schema, agent_settings.prompt_max_tokens // 2)
    prompt = prompt_registry.sql_generation(schema, question)

    response_dict = with_retry(
        call_agent_llm,
        prompt,
        tier="routing",
        tenant_id=tenant_id,
    )
    content = response_dict.get("content", response_dict.get("text", "")).strip()

    try:
        parsed = SQLQuery.model_validate_json(extract_first_json_block(content))
        sql = parsed.sql.rstrip(";").strip()
    except Exception:
        sql = content.rstrip(";").strip()
        if sql.startswith("```"):
            sql = extract_first_json_block(f"```\n{sql}\n```") or sql
            sql = sql.rstrip(";").strip()

    if not sql.lower().startswith("select"):
        raise ValueError("Generated SQL is not a SELECT statement")

    logger.info("Generated SQL (%d chars)", len(sql))
    return sql
