"""SQL generation using structured LLM output."""

from __future__ import annotations

import logging

from app.agent.tools.sql_engine.schema_provider import get_schema_description
from app.agent.utils.parsing import extract_first_json_block
from app.agent.utils.retry import with_retry
from app.services.llm_runner import call_llama
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SQLQuery(BaseModel):
    sql: str = Field(description="PostgreSQL SELECT query only")


_FORMAT = (
    '{"sql": "SELECT ... FROM ... WHERE ..."}'
)


def generate_sql(question: str) -> str:
    schema = get_schema_description()

    prompt = f"""You are a SQL generator for a SaaS multi-tenant system.

RULES:
- Only generate SELECT queries.
- NEVER use UPDATE, DELETE, INSERT, DROP, or ALTER.
- Do not hallucinate tables or columns.
- tenant_id filtering is added automatically; do not hard-code tenant values.
- Return ONLY JSON matching this schema: {_FORMAT}

DATABASE SCHEMA:
{schema}

QUESTION:
{question}
"""

    response_dict = with_retry(call_llama, prompt)
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
