"""Tests for action loop detection in router."""

from app.agent.core.router import _detect_action_loop, _extract_action_history
from app.agent.utils.state_helpers import create_initial_state


def test_detect_identical_repeat():
    assert _detect_action_loop(["sql", "sql"]) is True


def test_detect_sql_retrieval_oscillation():
    assert _detect_action_loop(["sql", "retrieval", "sql", "retrieval"]) is True


def test_no_loop_on_normal_progression():
    assert _detect_action_loop(["sql", "finish"]) is False


def test_extract_action_history_from_observations():
    state = create_initial_state("q", "t")
    state["observation_history"] = [
        "Decomposed into 1 sub-question(s)",
        "Decision = sql",
        "Decision = finish",
    ]
    assert _extract_action_history(state) == ["sql", "finish"]
