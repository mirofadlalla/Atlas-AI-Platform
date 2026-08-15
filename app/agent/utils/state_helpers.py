"""State resolution, initialization, and budget helpers."""

from __future__ import annotations

import time
import uuid
from typing import Any

from app.agent.core.config import agent_settings
from app.agent.core.state import AgentState, SubAnswer

PER_SUBQUESTION_RESET: dict[str, Any] = {
    "sql_result": None,
    "last_sql": None,
    "retrieval_context": None,
    "sql_attempted": False,
    "sql_has_results": False,
    "retrieval_attempted": False,
    "step_count": 0,
    "degraded": False,
    "degraded_reason": None,
    # Reset per-subquestion so the loop detector's sliding window only sees
    # actions from the *current* sub-question — not a mix of prior ones.
    "action_history": [],
}


def get_current_question(state: AgentState) -> str:
    subs = state.get("sub_questions") or [state.get("question", "")]
    idx = state.get("current_sub_question_index", 0)
    if idx < len(subs):
        return subs[idx]
    return state.get("question", "")


def create_initial_state(
    question: str,
    tenant_id: str | int,
    run_id: str | None = None,
    user_id: str | int | None = None,
    session_id: str | None = None,
) -> AgentState:
    return {
        "question": question,
        "tenant_id": str(tenant_id),
        "user_id": str(user_id) if user_id is not None else "",
        "session_id": session_id,
        "conversation_history": [],
        "recalled_memories": [],
        "episode_context": "",
        "working_memory_tokens": 0,
        "context_sources": [],
        "run_id": run_id or str(uuid.uuid4()),
        "start_time": time.time(),
        "thoughts": [],
        "observation_history": [],
        "step_count": 0,
        "total_step_count": 0,
        "total_cost": 0.0,
        "llm_cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "thought": None,
        "last_action": None,
        "observation": None,
        "last_sql": None,
        "retrieval_context": None,
        "sql_result": None,
        "final_answer": None,
        "original_question": None,
        "sub_questions": [],
        "sub_answers": [],
        "current_sub_question_index": 0,
        "sql_attempted": False,
        "sql_has_results": False,
        "retrieval_attempted": False,
        "retrieval_has_results": False,
        "degraded": False,
        "degraded_reason": None,
        "data_sources": [],
        "action_history": [],
        "tool_observations": [],
    }


def is_timed_out(state: AgentState) -> bool:
    """
    Check if the agent has exceeded its allowed execution time.
    """
    start = state.get("start_time")
    if start is None:
        return False
    return (time.time() - start) > agent_settings.agent_timeout_seconds


def budget_exceeded(state: AgentState) -> tuple[bool, str | None]:
    """ """
    if is_timed_out(state):
        return True, "Agent execution timed out"

    subs = state.get("sub_questions") or [state.get("question", "")]
    if len(subs) > agent_settings.max_subquestions:
        return True, f"Exceeded max sub-questions ({agent_settings.max_subquestions})"

    total_steps = state.get("total_step_count", 0)
    if total_steps >= agent_settings.max_total_steps:
        return True, f"Exceeded max total steps ({agent_settings.max_total_steps})"

    return False, None


def budget_exceeded_update(state: AgentState) -> dict[str, Any] | None:
    exceeded, reason = budget_exceeded(state)
    if not exceeded:
        return None
    return {
        "degraded": True,
        "degraded_reason": reason,
        "last_action": "finish",
    }


def per_subquestion_reset() -> dict[str, Any]:
    return dict(PER_SUBQUESTION_RESET)


def append_sub_answer(
    sub_answers: list[SubAnswer], question: str, answer: str
) -> list[SubAnswer]:
    updated = list(sub_answers)
    updated.append(SubAnswer(question=question, answer=answer))
    return updated
