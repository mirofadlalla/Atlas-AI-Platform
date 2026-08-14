"""Decompose node: breaks down complex questions into sub-questions."""

import json
import logging

from app.agent.core.config import agent_settings
from app.agent.core.state import AgentState
from app.agent.nodes.base import (
    emit_node_status,
    emit_thought_chunk,
    format_history,
    format_memories,
    run_node,
)
from app.agent.observability.logging import log_node_event
from app.agent.prompts.registry import prompt_registry
from app.agent.utils.llm import async_call_agent_llm_stream, llm_usage_updates
from app.agent.utils.parsing import extract_first_json_block

logger = logging.getLogger(__name__)


async def decompose_node(state: AgentState) -> dict:
    """
    Decompose a complex user question into smaller sub-questions for multi-step reasoning.

    Args:
        state (AgentState): State containing 'question', 'conversation_history',
            'recalled_memories', and 'episode_context'.

    Returns:
        dict: State update dictionary containing 'sub_questions', 'current_sub_question_index',
            'original_question', and 'sub_answers'.

    Example:
        >>> state = {"question": "How many users signed up last month and what was total revenue?"}
        >>> res = await decompose_node(state)
        >>> res["sub_questions"]
        ['How many users signed up last month?', 'What was the total revenue last month?']
    """
    await emit_node_status(
        "decompose",
        "Question Decomposition",
        "Analyzing and decomposing question into sub-questions...",
    )

    async def _inner(s: AgentState):
        question = s.get("question", "")
        prompt = prompt_registry.decompose(
            question,
            format_history(s.get("conversation_history", [])),
            format_memories(s.get("recalled_memories", [])),
            s.get("episode_context", ""),
        )
        try:
            response_dict = await async_call_agent_llm_stream(
                prompt=prompt,
                tier="routing",
                tenant_id=s.get("tenant_id"),
                event_type="stream_thought_chunk",
            )
            parsed = json.loads(extract_first_json_block(response_dict["content"]))
            sub_questions = parsed.get("sub_questions") or [question]
        except Exception as exc:
            logger.error("Decompose failed: %s", exc)
            sub_questions = [question]
            response_dict = {}

        if not sub_questions:
            sub_questions = [question]

        degraded = False
        degraded_reason = None
        if len(sub_questions) > agent_settings.max_subquestions:
            sub_questions = sub_questions[: agent_settings.max_subquestions]
            degraded = True
            degraded_reason = (
                f"Trimmed to {agent_settings.max_subquestions} sub-questions"
            )

        await emit_thought_chunk(
            f"\n[Decompose] Sub-question(s) created ({len(sub_questions)}):\n"
            + "\n".join(f"  {i+1}. {sq}" for i, sq in enumerate(sub_questions))
            + "\n"
        )

        update = {
            "original_question": question,
            "sub_questions": sub_questions,
            "current_sub_question_index": 0,
            "sub_answers": [],
            "degraded": degraded,
            "degraded_reason": degraded_reason,
            "observation_history": s.get("observation_history", [])
            + [f"Decomposed into {len(sub_questions)} sub-question(s)"],
        }
        if response_dict:
            update.update(llm_usage_updates(response_dict, s))

        log_node_event(logger, s, "decompose", "completed", parts=len(sub_questions))
        return update

    return await run_node("decompose", state, _inner)
