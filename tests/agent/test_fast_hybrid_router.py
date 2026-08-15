import pytest
from app.agent.core.intent_regex_pattern import calculate_deterministic_route
from app.agent.core.router import (
    evaluate_tool_sufficiency,
    fast_hybrid_router,
    route_target_path,
)
from app.agent.utils.state_helpers import create_initial_state


def test_calculate_deterministic_route_greetings():
    assert calculate_deterministic_route("Hello!") == "GREETING"
    assert calculate_deterministic_route("السلام عليكم") == "GREETING"


def test_calculate_deterministic_route_obvious_sql():
    assert (
        calculate_deterministic_route("How many users signed up last month?")
        == "OBVIOUS_SQL"
    )
    assert (
        calculate_deterministic_route("كم عدد المستخدمين المسجلين الشهر الماضي؟")
        == "OBVIOUS_SQL"
    )


def test_calculate_deterministic_route_obvious_retrieval():
    assert (
        calculate_deterministic_route("What is our refund policy document?")
        == "OBVIOUS_RETRIEVAL"
    )
    assert (
        calculate_deterministic_route("ما هي سياسة الاسترجاع الخاصة بالشركة؟")
        == "OBVIOUS_RETRIEVAL"
    )


def test_calculate_deterministic_route_conflicting_ambiguous():
    assert (
        calculate_deterministic_route(
            "What is the policy for users who signed up last month?"
        )
        == "AMBIGUOUS"
    )


@pytest.mark.asyncio
async def test_fast_hybrid_router_greetings_zero_llm_calls():
    state = create_initial_state("Hello!", "tenant-1")
    res = await fast_hybrid_router(state)
    assert res["intent"] == "GREETING"
    assert res["direct_response"] is not None


@pytest.mark.asyncio
async def test_fast_hybrid_router_obvious_sql():
    state = create_initial_state(
        "How many active users signed up last month?", "tenant-1"
    )
    res = await fast_hybrid_router(state)
    assert res["intent"] == "SIMPLE_SQL"
    assert res["direct_response"] is None


@pytest.mark.asyncio
async def test_fast_hybrid_router_obvious_retrieval():
    state = create_initial_state("What is our refund policy document?", "tenant-1")
    res = await fast_hybrid_router(state)
    assert res["intent"] == "SIMPLE_RETRIEVAL"
    assert res["direct_response"] is None


def test_route_target_path_direct_mapping():
    assert route_target_path({"intent": "SIMPLE_SQL"}) == "sql_tool"
    assert route_target_path({"intent": "SIMPLE_RETRIEVAL"}) == "retrieval_tool"
    assert route_target_path({"intent": "GREETING"}) == "direct_answer"
    assert route_target_path({"intent": "COMPLEX"}) == "decompose"


def test_evaluate_tool_sufficiency_single_sql():
    state = {
        "intent": "SIMPLE_SQL",
        "sql_has_results": True,
        "degraded": False,
    }
    assert evaluate_tool_sufficiency(state) == "SUFFICIENT"


def test_evaluate_tool_sufficiency_failed_sql():
    state = {
        "intent": "SIMPLE_SQL",
        "sql_has_results": False,
        "degraded": True,
    }
    assert evaluate_tool_sufficiency(state) == "INSUFFICIENT"
