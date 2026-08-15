"""Thought node: decides the agent's next reasoning action."""

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
from app.agent.prompts.registry import prompt_registry
from app.agent.schemas import ActionDecision
from app.agent.tools.base import tool_registry
from app.agent.utils.classification import classify_question_type
from app.agent.utils.llm import async_call_agent_llm_stream, llm_usage_updates
from app.agent.utils.parsing import extract_first_json_block
from app.agent.utils.state_helpers import get_current_question

logger = logging.getLogger(__name__)


def parse_action_decision(response_text: str) -> str:
    """
    Parse JSON action decision from LLM response.

    Args:
        response_text (str): Raw string response containing a JSON block.

    Returns:
        str: Chosen action ('sql', 'retrieval', or 'finish').
    """
    try:
        action_decision = ActionDecision.model_validate_json(
            extract_first_json_block(response_text)
        )
        action = action_decision.action.lower().strip()
        if action in tool_registry.list_tools() + ["finish"]:
            return action
    except Exception as exc:
        logger.warning("Could not parse action decision: %s", exc)
    return "finish"


async def thought_node(state: AgentState) -> dict:
    """
    Evaluate gathered observations and decide the next tool action or synthesis step.

    Args:
        state (AgentState): State containing question, step counts, and tool execution flags.

    Returns:
        dict: State update dictionary containing 'thought', 'last_action', 'step_count',
            and 'action_history'.

    Example:
        >>> state = {"question": "How many users are active?", "step_count": 0}
        >>> res = await thought_node(state)
        >>> res["last_action"]
        'sql'
    """
    await emit_node_status(
        "think",
        "Thinking",
        "Reasoning next action...",
    )

    async def _inner(s: AgentState):
        has_sql = bool(s.get("last_sql"))
        has_retrieval = bool(s.get("retrieval_context"))
        actions = []
        if has_sql:
            actions.append("SQL already executed")
        if has_retrieval:
            actions.append("Retrieval already executed")
        actions_context = "\n".join(actions) if actions else "None"

        current_question = get_current_question(s)
        question_type = classify_question_type(current_question)
        guidance = {
            "data": "Use SQL",
            "knowledge": "Use RETRIEVAL",
        }.get(question_type, "Decide best action")

        prompt = prompt_registry.thought(
            current_question,
            s.get("step_count", 0),
            actions_context,
            guidance,
            format_history(s.get("conversation_history", [])),
            format_memories(s.get("recalled_memories", [])),
            s.get("episode_context", ""),
        )
        try:
            response = await async_call_agent_llm_stream(
                prompt=prompt,
                tier="generation",
                tenant_id=s.get("tenant_id"),
                event_type="stream_thought_chunk",
            )
            next_action = parse_action_decision(response["content"])
            thought = response["content"]
        except Exception as exc:
            logger.error("Thought node LLM failure: %s", exc)
            next_action = "finish"
            thought = f"LLM error, finishing early: {exc}"
            await emit_thought_chunk(f"\n[Thinking Error] {thought}\n")
            return {
                "thought": thought,
                "last_action": next_action,
                "step_count": s.get("step_count", 0) + 1,
                "total_step_count": s.get("total_step_count", 0) + 1,
                "action_history": s.get("action_history", []) + [next_action],
                "degraded": True,
                "degraded_reason": "LLM call failed during reasoning",
                "observation_history": s.get("observation_history", [])
                + [f"Decision = {next_action} (degraded)"],
            }

        await emit_thought_chunk(f"\n[Decision] Action chosen: {next_action.upper()}\n")

        step = s.get("step_count", 0) + 1
        total = s.get("total_step_count", 0) + 1
        update: dict = {
            "thought": thought,
            "last_action": next_action,
            "step_count": step,
            "total_step_count": total,
            "action_history": s.get("action_history", []) + [next_action],
            "observation_history": s.get("observation_history", [])
            + [f"Decision = {next_action}"],
            **llm_usage_updates(response, s),
        }
        if step >= agent_settings.max_steps_per_subquestion:
            update["degraded"] = True
            update["degraded_reason"] = "Step limit reached for sub-question"
        return update

    return await run_node("think", state, _inner)
