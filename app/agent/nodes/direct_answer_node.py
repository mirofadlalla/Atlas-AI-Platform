"""Direct answer node for greetings and general QA without tools."""

import logging

from app.agent.core.state import AgentState
from app.agent.nodes.base import (
    emit_answer_chunk,
    emit_node_status,
    format_history,
    format_memories,
    run_node,
)
from app.agent.utils.llm import async_call_agent_llm_stream

logger = logging.getLogger(__name__)


async def direct_answer_node(state: AgentState) -> dict:
    """
    Handle greetings, meta-questions, or direct general QA without tools.

    If ``state`` contains a pre-built ``direct_response`` (e.g. greeting from
    the router) it is emitted directly.  Otherwise, an LLM is called with the
    full conversation context — history, recalled memories, and episodic session
    summaries — so follow-up questions receive coherent, context-aware answers.
    """
    await emit_node_status(
        "direct_answer",
        "Direct Answer",
        "Formulating answer...",
    )

    async def _inner(s: AgentState):
        direct = s.get("direct_response")
        if direct:
            await emit_answer_chunk(direct)
            return {"final_answer": direct}

        question = s.get("question", "")

        # Build context block exactly as finish_node and thought_node do, so
        # follow-up DIRECT_QA questions are coherent rather than context-blind.
        chat_history = format_history(s.get("conversation_history") or [])
        memories = format_memories(s.get("recalled_memories") or [])
        episode_ctx = s.get("episode_context") or ""

        context_parts: list[str] = []
        if chat_history:
            context_parts.append(f"CONVERSATION HISTORY:\n{chat_history}")
        if memories:
            context_parts.append(f"RELEVANT USER MEMORIES:\n{memories}")
        if episode_ctx:
            context_parts.append(f"RECENT SESSION SUMMARIES:\n{episode_ctx}")

        context_block = "\n\n".join(context_parts)
        prompt = (
            f"{context_block}\n\n" if context_block else ""
        ) + f"QUESTION: {question}\n\nAnswer clearly and concisely:"

        response_dict = await async_call_agent_llm_stream(
            prompt=prompt,
            tier="generation",
            tenant_id=s.get("tenant_id"),
            event_type="stream_answer_chunk",
        )
        return {"final_answer": response_dict["content"].strip()}

    return await run_node("direct_answer", state, _inner)
