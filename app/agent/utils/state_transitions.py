"""Post-sub-question state transitions (index advance + per-question reset)."""

from __future__ import annotations

from typing import Any

from app.agent.core.state import AgentState
from app.agent.utils.state_helpers import (
    append_sub_answer,
    get_current_question,
    per_subquestion_reset,
)


def build_subquestion_answer_update(
    state: AgentState,
    sub_answer_text: str,
    data_sources: list[str],
) -> dict[str, Any]:
    """Advance sub-question index and reset per-question tool state."""
    current_idx = state.get("current_sub_question_index", 0)
    current_question = get_current_question(state)
    sub_answers = append_sub_answer(
        list(state.get("sub_answers", [])),
        current_question,
        sub_answer_text,
    )

    update: dict[str, Any] = {
        "sub_answers": sub_answers,
        "current_sub_question_index": current_idx + 1,
        **per_subquestion_reset(),
        "observation_history": state.get("observation_history", [])
        + [f"Answered part {current_idx + 1}: {sub_answer_text[:100]}..."],
        "data_sources": data_sources,
    }
    if state.get("degraded"):
        update["degraded"] = True
        update["degraded_reason"] = state.get("degraded_reason")
    return update


def should_synthesize_final(state: AgentState) -> bool:
    subs = state.get("sub_questions") or [state.get("question", "")]
    idx = state.get("current_sub_question_index", 0)
    return idx >= len(subs) - 1


def is_single_subquestion(state: AgentState) -> bool:
    subs = state.get("sub_questions") or [state.get("question", "")]
    return len(subs) == 1
