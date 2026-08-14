"""Retrieval tool execution node."""

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
from app.agent.tools.base import tool_registry
from app.agent.tools.retrieval_tool import RetrievalTool

logger = logging.getLogger(__name__)

tool_registry.register(RetrievalTool())


async def retrieval_node(state: AgentState) -> dict:
    """
    Retrieve relevant documents from the vector database using the RetrievalTool.

    Args:
        state (AgentState): State containing question, tenant_id, and query parameters.

    Returns:
        dict: State update dictionary containing document retrieval context and observations.

    Example:
        >>> state = {"question": "What is the return policy?", "tenant_id": "tenant-1"}
        >>> res = await retrieval_node(state)
        >>> res["observation"]
        'Retrieved 3 document(s)'
    """
    await emit_node_status(
        "retrieval_tool",
        "Document Retrieval",
        "Searching knowledge base for relevant context...",
    )

    async def _inner(s: AgentState):
        tool = tool_registry.get("retrieval")
        assert tool is not None
        result = await asyncio.to_thread(tool.run, s)
        update = apply_tool_result(s, result, "retrieval")

        await emit_thought_chunk(
            f"[Document Retrieval] Search completed. Observation: {result.observation[:300]}\n"
        )
        log_node_event(
            logger, s, "retrieval_tool", "completed", has_data=result.has_data
        )
        return update

    return await run_node("retrieval_tool", state, _inner)
