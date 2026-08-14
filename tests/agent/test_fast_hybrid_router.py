import pytest
from app.agent.core.router import (
    evaluate_tool_sufficiency,
    fast_hybrid_router,
    route_initial_intent,
)
from app.agent.utils.state_helpers import create_initial_state


@pytest.mark.asyncio
async def test_fast_hybrid_router_greetings_zero_llm_calls():
    state = create_initial_state("Hello!", "tenant-1")
    res = await fast_hybrid_router(state)
    assert res["intent"] == "GREETING"
    assert res["direct_response"] is not None
    assert res["needs_short_term"] is False


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


def test_route_initial_intent_without_memory():
    state = {
        "intent": "SIMPLE_SQL",
        "needs_short_term": False,
        "needs_semantic": False,
        "needs_episodic": False,
    }
    assert route_initial_intent(state) == "sql_tool"


def test_route_initial_intent_with_memory():
    state = {
        "intent": "SIMPLE_SQL",
        "needs_short_term": True,
        "needs_semantic": False,
        "needs_episodic": False,
    }
    assert route_initial_intent(state) == "memory_loader"


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
