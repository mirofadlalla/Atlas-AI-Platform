"""SQL tool execution node."""

import asyncio
import logging

from app.agent.core.state import AgentState
from app.agent.nodes.base import (
    apply_tool_result,
    emit_node_status,
    emit_thought_chunk,
    run_node,
)
from app.agent.observability.logging import log_node_event
from app.agent.observability.metrics import agent_sql_rows_returned
from app.agent.tools.base import tool_registry
from app.agent.tools.sql_tool import SQLTool

logger = logging.getLogger(__name__)

tool_registry.register(SQLTool())


async def sql_node(state: AgentState) -> dict:
    """
    Execute SQL queries against the database using the SQLTool.

    Args:
        state (AgentState): State containing question, tenant_id, and history context.

    Returns:
        dict: State update dictionary containing SQL execution observations and state updates.

    Example:
        >>> state = {"question": "How many rows in users?", "tenant_id": "tenant-1"}
        >>> res = await sql_node(state)
        >>> res["observation"]
        'SQL query returned 1 rows'
    """
    await emit_node_status(
        "sql_tool",
        "SQL Query",
        "Formulating and executing SQL database query...",
    )

    async def _inner(s: AgentState):
        tool = tool_registry.get("sql")
        assert tool is not None
        result = await asyncio.to_thread(tool.run, s)
        update = apply_tool_result(s, result, "sql")
        if result.has_data:
            agent_sql_rows_returned.observe(1)

        await emit_thought_chunk(
            f"[SQL Query] Executed database query. Observation: {result.observation[:300]}\n"
        )
        log_node_event(logger, s, "sql_tool", "completed", has_data=result.has_data)
        return update

    return await run_node("sql_tool", state, _inner)
