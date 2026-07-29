import time

from app.agent.utils.state_helpers import (
    budget_exceeded,
    create_initial_state,
    get_current_question,
    per_subquestion_reset,
)


def test_get_current_question_uses_sub_question_index():
    state = create_initial_state("original", "tenant-1")
    state["sub_questions"] = ["part one", "part two"]
    state["current_sub_question_index"] = 1
    assert get_current_question(state) == "part two"


def test_get_current_question_falls_back_to_original():
    state = create_initial_state("fallback question", "tenant-1")
    assert get_current_question(state) == "fallback question"


def test_per_subquestion_reset_includes_retrieval_attempted():
    reset = per_subquestion_reset()
    assert reset["retrieval_attempted"] is False
    assert reset["sql_attempted"] is False


def test_budget_exceeded_on_timeout():
    state = create_initial_state("q", "t")
    state["start_time"] = time.time() - 9999
    exceeded, reason = budget_exceeded(state)
    assert exceeded is True
    assert reason is not None
