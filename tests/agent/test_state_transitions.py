from app.agent.utils.state_transitions import (
    build_subquestion_answer_update,
    is_single_subquestion,
    should_synthesize_final,
)
from app.agent.utils.state_helpers import create_initial_state


def test_build_subquestion_answer_update_resets_retrieval():
    state = create_initial_state("q", "t")
    state["sub_questions"] = ["part one", "part two"]
    state["retrieval_attempted"] = True
    update = build_subquestion_answer_update(state, "answer one", ["DATABASE"])
    assert update["retrieval_attempted"] is False
    assert update["current_sub_question_index"] == 1


def test_should_synthesize_final_on_last_index():
    state = create_initial_state("q", "t")
    state["sub_questions"] = ["a", "b"]
    state["current_sub_question_index"] = 1
    assert should_synthesize_final(state) is True


def test_is_single_subquestion():
    state = create_initial_state("q", "t")
    state["sub_questions"] = ["only one"]
    assert is_single_subquestion(state) is True
