"""SQL tool execution node."""

import asyncio
import logging

from app.agent.core.config import agent_settings
from app.agent.core.state import AgentState
from app.agent.nodes.base import (
    apply_tool_result,
    emit_node_status,
    emit_thought_chunk,
    run_node,
)
from app.agent.observability.logging import log_node_event
from app.agent.observability.metrics import agent_sql_rows_returned
from app.agent.tools.base import ToolResult, tool_registry
from app.agent.tools.sql_tool import SQLTool

logger = logging.getLogger(__name__)

tool_registry.register(SQLTool())


async def sql_node(state: AgentState) -> dict:
    """
    Execute SQL queries against the database using the SQLTool.

    A hard ``asyncio.wait_for`` timeout wraps the blocking ``tool.run`` call so
    the event loop is never held indefinitely even when the DB hangs before the
    ``SET LOCAL statement_timeout`` is applied (e.g. during lock contention or
    connection-pool exhaustion).
    """
    await emit_node_status(
        "sql_tool",
        "SQL Query",
        "Formulating and executing SQL database query...",
    )

    async def _inner(s: AgentState):
        tool = tool_registry.get("sql")
        if tool is None:
            raise RuntimeError("SQL tool is not registered in the tool registry")

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(tool.run, s),
                timeout=agent_settings.sql_query_timeout_seconds,
            )
        except asyncio.TimeoutError:
            timeout_s = agent_settings.sql_query_timeout_seconds
            logger.error("SQL tool timed out after %.1fs", timeout_s)
            result = ToolResult(
                observation=(
                    f"Error: SQL query timed out after {timeout_s:.0f}s. "
                    "The database may be under heavy load."
                ),
                has_data=False,
                state_updates={
                    "sql_attempted": True,
                    "sql_has_results": False,
                    "degraded": True,
                    "degraded_reason": f"SQL query timed out after {timeout_s:.0f}s",
                },
            )

        update = apply_tool_result(s, result, "sql")
        if result.has_data:
            agent_sql_rows_returned.observe(1)

        await emit_thought_chunk(
            f"[SQL Query] Executed database query. Observation: {result.observation[:300]}\n"
        )
        log_node_event(logger, s, "sql_tool", "completed", has_data=result.has_data)
        return update

    return await run_node("sql_tool", state, _inner)
