"""Retrieval tool execution node."""

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
from app.agent.tools.base import ToolResult, tool_registry
from app.agent.tools.retrieval_tool import RetrievalTool

logger = logging.getLogger(__name__)

tool_registry.register(RetrievalTool())


async def retrieval_node(state: AgentState) -> dict:
    """
    Retrieve relevant documents from the vector database using the RetrievalTool.

    A hard ``asyncio.wait_for`` timeout wraps the blocking ``tool.run`` call so
    the event loop is never held indefinitely if the vector store hangs (e.g.
    during index rebuilds or network issues).
    """
    await emit_node_status(
        "retrieval_tool",
        "Document Retrieval",
        "Searching knowledge base for relevant context...",
    )

    async def _inner(s: AgentState):
        tool = tool_registry.get("retrieval")
        if tool is None:
            raise RuntimeError("Retrieval tool is not registered in the tool registry")

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(tool.run, s),
                timeout=agent_settings.retrieval_timeout_seconds,
            )
        except asyncio.TimeoutError:
            timeout_s = agent_settings.retrieval_timeout_seconds
            logger.error("Retrieval tool timed out after %.1fs", timeout_s)
            result = ToolResult(
                observation=(
                    f"Error: Document retrieval timed out after {timeout_s:.0f}s. "
                    "The vector store may be under heavy load."
                ),
                has_data=False,
                state_updates={
                    "retrieval_attempted": True,
                    "retrieval_has_results": False,
                    "degraded": True,
                    "degraded_reason": f"Retrieval timed out after {timeout_s:.0f}s",
                },
            )

        update = apply_tool_result(s, result, "retrieval")

        await emit_thought_chunk(
            f"[Document Retrieval] Search completed. Observation: {result.observation[:300]}\n"
        )
        log_node_event(
            logger, s, "retrieval_tool", "completed", has_data=result.has_data
        )
        return update

    return await run_node("retrieval_tool", state, _inner)
