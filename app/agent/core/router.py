"""Conditional routing and loop control for the agent graph."""

from __future__ import annotations

import logging

from app.agent.core.config import agent_settings
from app.agent.core.state import AgentState
from app.agent.tools.base import tool_registry
from app.agent.utils.classification import classify_question_type
from app.agent.utils.state_helpers import get_current_question

logger = logging.getLogger(__name__)


def _tool_attempted(state: AgentState, tool_name: str) -> bool:
    tool = tool_registry.get(tool_name)
    if not tool:
        return False
    return bool(state.get(tool.attempted_key, False))


def _extract_action_history(state: AgentState) -> list[str]:
    stored = state.get("action_history")
    if stored:
        return list(stored)

    actions: list[str] = []
    for obs in state.get("observation_history", []):
        if obs.startswith("Decision = "):
            action = obs.replace("Decision = ", "").split(" ")[0].strip()
            if action:
                actions.append(action)
    return actions


def _detect_action_loop(actions: list[str]) -> bool:
    """Detect identical repeats or sql↔retrieval oscillation."""
    window = agent_settings.loop_detection_window
    recent = actions[-window:]
    if len(recent) >= 2 and recent[-1] == recent[-2]:
        return True

    if len(recent) >= 4:
        a, b, c, d = recent[-4], recent[-3], recent[-2], recent[-1]
        if a == c and b == d and a != b:
            return True

    if len(recent) >= 6:
        pattern = recent[-3:]
        prev = recent[-6:-3]
        if pattern == prev:
            return True

    return False


def route_action(state: AgentState) -> str:
    """Return the next node name based on agent state."""
    last_action = state.get("last_action", "finish")
    step_count = state.get("step_count", 0)
    observation_history = state.get("observation_history", [])
    current_question = get_current_question(state)
    question_type = classify_question_type(current_question)

    has_sql_results = state.get("sql_has_results", False)
    has_retrieval_data = state.get("retrieval_has_results", False) or bool(
        state.get("retrieval_context")
    )

    if state.get("degraded") and last_action == "finish":
        logger.info("Degraded run → finish")
        return "finish"

    if step_count >= agent_settings.max_steps_per_subquestion:
        logger.info("Max steps per sub-question reached → finish")
        return "finish"

    if last_action not in tool_registry.list_tools() + ["finish"]:
        return "finish"

    if (
        len(observation_history) >= 2
        and observation_history[-1] == observation_history[-2]
    ):
        logger.info("Repeated observation → finish")
        return "finish"

    if _detect_action_loop(_extract_action_history(state)):
        logger.info("Action loop detected → finish")
        return "finish"

    if last_action == "sql" and has_sql_results:
        return "finish"

    if last_action == "retrieval" and has_retrieval_data:
        return "finish"

    if last_action == "sql" and _tool_attempted(state, "sql") and not has_sql_results:
        if not _tool_attempted(state, "retrieval"):
            logger.info("SQL failed → trying retrieval")
            return "retrieval"
        return "finish"

    if (
        last_action == "retrieval"
        and _tool_attempted(state, "retrieval")
        and not has_retrieval_data
    ):
        return "finish"

    if last_action == "finish":
        if question_type == "data" and not has_sql_results:
            logger.info("Forcing SQL for data question")
            return "sql"
        if question_type == "knowledge" and not has_retrieval_data:
            logger.info("Forcing retrieval for knowledge question")
            return "retrieval"

    return last_action


def route_after_finish(state: AgentState) -> str:
    idx = state.get("current_sub_question_index", 0)
    subs = state.get("sub_questions", [])
    if idx < len(subs):
        logger.info("Next sub-question %s/%s", idx + 1, len(subs))
        return "think"
    logger.info("All sub-questions complete")
    return "end"
