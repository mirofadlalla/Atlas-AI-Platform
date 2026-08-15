"""SQL tool implementation."""

from __future__ import annotations

import logging
from sqlalchemy import text

from app.agent.core.config import agent_settings
from app.agent.core.state import AgentState
from app.agent.tools.base import AgentTool, ToolResult
from app.agent.tools.sql_engine.sql_generator import generate_sql
from app.agent.tools.sql_engine.validator import SQLValidator
from app.agent.utils.result_formatting import format_sql_results
from app.agent.utils.state_helpers import get_current_question
from app.core.db import get_db_session
from app.services.tenant_database_service import TenantDatabaseError, tenant_database_manager

logger = logging.getLogger(__name__)


class SQLTool(AgentTool):
    name = "sql"
    attempted_key = "sql_attempted"
    has_data_key = "sql_has_results"

    def run(self, state: AgentState) -> ToolResult:
        question = get_current_question(state)
        try:
            # The tenant id is populated from the authenticated controller, never LLM output.
            tenant_id = state["tenant_id"]
            with get_db_session() as atlas_db:
                metadata = tenant_database_manager.schema(atlas_db, tenant_id)
                tables = metadata["tables"]
                schema_text = "\n".join(
                    f"{name}(" + ", ".join(f"{c['name']} {c['type']}" for c in value["columns"]) + ")"
                    for name, value in tables.items()
                )
                relationships = metadata.get("relationships", [])
                if relationships:
                    schema_text += "\n\nRELATIONSHIPS:\n" + "\n".join(
                        f"{r['from_table']}.{', '.join(r['from_columns'])} -> "
                        f"{r['to_table']}.{', '.join(r['to_columns'])}"
                        for r in relationships
                    )
                allowed_columns = {column["name"] for value in tables.values() for column in value["columns"]}
                raw_sql = generate_sql(question, tenant_id=tenant_id, schema=schema_text)
                config = tenant_database_manager._configuration(atlas_db, tenant_id)
                dialect = "mysql" if config.database_type == "mysql" else "postgres"
            safe_sql, params = SQLValidator.validate_and_enforce_tenant(
                raw_sql,
                tenant_id,
                allowed_tables=set(tables),
                allowed_columns=allowed_columns,
                inject_tenant_filter=False,
                dialect=dialect,
            )
            with get_db_session() as atlas_db, tenant_database_manager.get_connection(atlas_db, tenant_id) as connection:
                if config.database_type == "postgresql":
                    connection.execute(text(f"SET LOCAL statement_timeout = '{int(agent_settings.sql_query_timeout_seconds * 1000)}'"))
                rows = list(connection.execute(text(safe_sql), params).fetchall())
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
                    "total_cost": state.get("total_cost", 0.0),
                },
            )
        except TenantDatabaseError as exc:
            logger.warning("Tenant SQL tool unavailable: %s", exc.code)
            return ToolResult(observation=f"Error: {exc.code}", state_updates={"sql_attempted": True, "sql_has_results": False})
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
