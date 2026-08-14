"""Direct answer node for greetings and general QA without tools."""

import logging

from app.agent.core.state import AgentState
from app.agent.nodes.base import emit_answer_chunk, emit_node_status, run_node
from app.agent.utils.llm import async_call_agent_llm_stream

logger = logging.getLogger(__name__)


async def direct_answer_node(state: AgentState) -> dict:
    """
    Handle greetings, meta-questions, or direct general QA without tools.
    If state contains direct_response, emits it. Otherwise streams a direct LLM response.
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
        response_dict = await async_call_agent_llm_stream(
            prompt=f"Answer the following question clearly and concisely:\n\n{question}",
            tier="generation",
            tenant_id=s.get("tenant_id"),
            event_type="stream_answer_chunk",
        )
        return {"final_answer": response_dict["content"].strip()}

    return await run_node("direct_answer", state, _inner)
