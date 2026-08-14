"""Finish node: synthesizes final answers for sub-questions or original question."""

import logging

from app.agent.core.state import AgentState
from app.agent.nodes.base import emit_node_status, run_node
from app.agent.nodes.finish_helpers import (
    async_answer_subquestion,
    async_synthesize_final_answer,
)
from app.agent.observability.logging import log_node_event
from app.agent.utils.llm import llm_usage_updates
from app.agent.utils.state_transitions import (
    build_subquestion_answer_update,
    is_single_subquestion,
    should_synthesize_final,
)

logger = logging.getLogger(__name__)


async def finish_node(state: AgentState) -> dict:
    """
    Synthesize answers for sub-questions and assemble the final response.

    Args:
        state (AgentState): State containing question, gathered observations, and sub-answers.

    Returns:
        dict: State update dictionary containing 'final_answer', 'sub_answers', and metrics updates.

    Example:
        >>> state = {
        ...     "question": "What is Python?",
        ...     "retrieval_context": "Python is a high-level programming language."
        ... }
        >>> res = await finish_node(state)
        >>> res["final_answer"]
        'Python is a high-level programming language.'
    """
    await emit_node_status(
        "finish",
        "Answer Synthesis",
        "Synthesizing answer...",
    )

    async def _inner(s: AgentState):
        try:
            (
                sub_answer_text,
                data_sources,
                llm_result,
                context_tokens,
                context_sources,
            ) = await async_answer_subquestion(s)
            next_state = build_subquestion_answer_update(
                s, sub_answer_text, data_sources
            )
            next_state.update(llm_usage_updates(llm_result, s))
            next_state.update(
                {
                    "working_memory_tokens": context_tokens,
                    "context_sources": context_sources,
                }
            )

            if should_synthesize_final(s):
                if is_single_subquestion(s):
                    next_state["final_answer"] = sub_answer_text
                else:
                    original = s.get("original_question", s.get("question", ""))
                    final, synth_result = await async_synthesize_final_answer(
                        original,
                        next_state["sub_answers"],
                        s.get("tenant_id"),
                    )
                    next_state["final_answer"] = final
                    next_state.update(
                        llm_usage_updates(synth_result, {**s, **next_state})
                    )

            log_node_event(
                logger,
                s,
                "finish",
                "completed",
                part=s.get("current_sub_question_index", 0) + 1,
            )
            return next_state
        except Exception as exc:
            logger.error("Finish node failed: %s", exc)
            return {
                "final_answer": f"I encountered an error while generating the answer: {exc}",
                "degraded": True,
                "degraded_reason": "Answer generation failed",
            }

    return await run_node("finish", state, _inner)
