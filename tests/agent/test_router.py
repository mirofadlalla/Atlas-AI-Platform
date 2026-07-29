from app.agent.core.router import route_action
from app.agent.nodes import tool_registry  # noqa: F401 — registers tools
from app.agent.utils.state_helpers import create_initial_state


def _base_state(**overrides):
    state = create_initial_state("how many users?", "tenant-1")
    state.update(
        {
            "sub_questions": ["how many users?"],
            "current_sub_question_index": 0,
            "step_count": 1,
            "last_action": "sql",
            "sql_attempted": True,
            "sql_has_results": False,
            "retrieval_attempted": True,
            **overrides,
        }
    )
    return state


def test_router_skips_retrieval_fallback_when_already_attempted():
    assert route_action(_base_state()) == "finish"


def test_router_offers_retrieval_after_failed_sql():
    state = _base_state(retrieval_attempted=False)
    assert route_action(state) == "retrieval"


def test_router_finishes_when_sql_has_results():
    state = _base_state(sql_has_results=True, last_action="sql")
    assert route_action(state) == "finish"
