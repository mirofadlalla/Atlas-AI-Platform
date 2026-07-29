"""SQL tool implementation."""

from __future__ import annotations

import logging

from app.agent.core.config import agent_settings
from app.agent.core.state import AgentState
from app.agent.tools.base import AgentTool, ToolResult
from app.agent.tools.sql_engine.sql_generator import generate_sql
from app.agent.tools.sql_engine.validator import SQLValidator
from app.agent.utils.result_formatting import format_sql_results
from app.agent.utils.state_helpers import get_current_question

logger = logging.getLogger(__name__)


class SQLTool(AgentTool):
    name = "sql"
    attempted_key = "sql_attempted"
    has_data_key = "sql_has_results"

    def run(self, state: AgentState) -> ToolResult:
        question = get_current_question(state)
        try:
            raw_sql = generate_sql(question)
            safe_sql, params = SQLValidator.validate_and_enforce_tenant(
                raw_sql,
                state["tenant_id"],
            )
            cost = SQLValidator.get_query_cost(safe_sql, params)

            if cost > agent_settings.sql_max_allowed_cost:
                msg = (
                    f"Error: Query is too expensive (cost={cost}). "
                    "Please ask a more specific question."
                )
                return ToolResult(
                    observation=msg,
                    state_updates={
                        "sql_attempted": True,
                        "sql_has_results": False,
                    },
                )

            rows = SQLValidator.execute_query(safe_sql, params)
            result_str, has_data = format_sql_results(rows)
            observation = f"[DATABASE] SQL executed:\n{result_str}"

            return ToolResult(
                observation=observation,
                has_data=has_data,
                state_updates={
                    "last_sql": safe_sql,
                    "sql_result": result_str if has_data else None,
                    "sql_attempted": True,
                    "sql_has_results": has_data,
                    "total_cost": state.get("total_cost", 0.0) + cost,
                },
            )
        except ValueError as exc:
            logger.error("SQL validation error: %s", exc)
            return ToolResult(
                observation=f"Error: {exc}",
                state_updates={"sql_attempted": True, "sql_has_results": False},
            )
        except Exception as exc:
            logger.error("SQL execution error: %s", exc)
            return ToolResult(
                observation=f"Error executing query: {exc}",
                state_updates={"sql_attempted": True, "sql_has_results": False},
            )
