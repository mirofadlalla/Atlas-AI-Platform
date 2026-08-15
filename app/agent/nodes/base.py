"""Base runner, tracing, metrics, and helper utilities for graph nodes."""

from __future__ import annotations

import logging
import time

try:
    from langchain_core.callbacks import adispatch_custom_event
except ImportError:  # CI pins langchain-core 0.1.x

    async def adispatch_custom_event(*_args, **_kwargs):
        return None


from app.agent.core.state import AgentState
from app.agent.observability.metrics import (
    agent_node_duration_seconds,
    agent_node_executions_total,
)
from app.agent.observability.tracing import trace_span
from app.agent.utils.state_helpers import budget_exceeded_update

logger = logging.getLogger(__name__)


async def emit_node_status(node_name: str, display_name: str, message: str):
    """Dispatch node status event for real-time streaming to client."""
    try:
        await adispatch_custom_event(
            "stream_node_status",
            {"node": node_name, "tool": display_name, "message": message},
        )
    except (RuntimeError, Exception):
        pass


async def emit_thought_chunk(chunk: str):
    """Dispatch word-by-word thought stream chunk."""
    if chunk:
        try:
            await adispatch_custom_event("stream_thought_chunk", {"content": chunk})
        except (RuntimeError, Exception):
            pass


async def emit_answer_chunk(chunk: str):
    """Dispatch word-by-word answer stream chunk."""
    if chunk:
        try:
            await adispatch_custom_event("stream_answer_chunk", {"content": chunk})
        except (RuntimeError, Exception):
            pass


def format_history(history: list[dict[str, str]]) -> str:
    return "\n".join(
        f"{turn.get('role', 'user').title()}: {turn.get('content', '')}"
        for turn in history
    )


def format_memories(memories: list[str]) -> str:
    return "\n".join(f"- {memory}" for memory in memories)


def apply_tool_result(state: AgentState, result, tool_name: str) -> dict:
    history = state.get("observation_history", [])
    obs_record = result.to_observation_record(tool_name)
    tool_observations = list(state.get("tool_observations", []))
    tool_observations.append(
        {
            "tool": obs_record.tool,
            "observation": obs_record.observation[:500],
            "has_data": obs_record.has_data,
        }
    )
    return {
        "observation": result.observation,
        "observation_history": history + [result.observation],
        "tool_observations": tool_observations,
        **result.state_updates,
    }


async def run_node(name: str, state: AgentState, fn):
    start = time.time()
    status = "success"
    with trace_span(
        name,
        run_id=state.get("run_id"),
        tenant_id=state.get("tenant_id"),
    ):
        try:
            if budget := budget_exceeded_update(state):
                return budget
            result = await fn(state)
            return result
        except Exception as exc:
            status = "error"
            logger.error("%s node failed: %s", name, exc, exc_info=True)
            raise
        finally:
            agent_node_executions_total.labels(node=name, status=status).inc()
            agent_node_duration_seconds.labels(node=name).observe(time.time() - start)
