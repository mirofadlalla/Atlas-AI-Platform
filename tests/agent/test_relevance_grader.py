"""
Tests for CRAG-style relevance grading node and fallback behavior.

Covers the 5 acceptance criteria:
1. DB question misrouted to retrieval -> falls through to sql_tool (bug repro).
2. Genuine doc question with relevant chunks -> goes to finish_node (happy path).
3. Chunks pass pre-filter but fail LLM grading -> fallback to sql_tool.
4. Pre-filter removes all chunks -> no LLM call is made -> fallback to sql_tool.
5. LLM grading raises exception -> fail-safe fallback to sql_tool without crashing.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.core.config import agent_settings
from app.agent.core.relevance_grader import (
    GradingResult,
    grade_retrieval_relevance,
)
from app.agent.core.router import evaluate_tool_sufficiency, route_action
from app.agent.core.state import AgentState
from app.agent.nodes.retrieval_node import retrieval_node
from app.agent.tools.base import ToolResult


# ── Test 1: DB/SQL-style question misrouted to retrieval (Bug Repro Fixed) ────
@pytest.mark.asyncio
async def test_db_question_misrouted_to_retrieval_falls_through_to_sql():
    """
    When a database question is misrouted to retrieval and returns irrelevant docs,
    relevance grading marks retrieval_has_results=False.
    evaluate_tool_sufficiency evaluates to INSUFFICIENT and route_action falls through to sql.
    """
    candidate_docs = [
        {"content": "Privacy policy and terms of service document...", "score": 0.85},
        {
            "content": "Employee handbook section 3 on holiday requests...",
            "score": 0.82,
        },
    ]

    mock_tool = MagicMock()
    mock_tool.run.return_value = ToolResult(
        observation="Retrieved 2 candidate docs",
        has_data=True,
        state_updates={
            "retrieval_context": "=== UNTRUSTED DATA ===\n...",
            "retrieval_attempted": True,
            "retrieval_has_results": True,
            "raw_retrieved_docs": candidate_docs,
        },
    )

    # LLM grades these documents as irrelevant for the SQL question
    mock_llm_response = {
        "content": json.dumps(
            {"relevant_indices": [], "reasoning": "None of the docs answer user count"}
        ),
        "input_tokens": 50,
        "output_tokens": 20,
        "cost_usd": 0.0001,
    }

    state: AgentState = {
        "question": "How many active users are registered in the database?",
        "intent": "SIMPLE_RETRIEVAL",
        "tenant_id": 1,
        "sql_attempted": False,
        "retrieval_attempted": False,
        "retrieval_has_results": False,
        "relevant_docs": [],
        "retrieval_context": None,
        "step_count": 0,
        "action_history": [],
        "observation_history": [],
    }

    with patch(
        "app.agent.nodes.retrieval_node.tool_registry.get", return_value=mock_tool
    ), patch(
        "app.agent.core.relevance_grader.async_call_agent_llm_stream",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = mock_llm_response

        # Execute retrieval node with CRAG grading
        updated_state = await retrieval_node(state)
        combined_state = {**state, **updated_state}

        # 1. State assertions
        assert combined_state["retrieval_has_results"] is False
        assert combined_state["relevant_docs"] == []
        assert combined_state["retrieval_context"] is None
        assert combined_state["retrieval_attempted"] is True

        # 2. Sufficiency check assertion
        sufficiency = evaluate_tool_sufficiency(combined_state)
        assert sufficiency == "INSUFFICIENT"

        # 3. Router action fallback assertion
        combined_state["last_action"] = "retrieval"
        next_action = route_action(combined_state)
        assert next_action == "sql"


# ── Test 2: Genuine Document Question (Happy Path) ────────────────────────────
@pytest.mark.asyncio
async def test_genuine_doc_question_with_relevant_chunks_routes_to_finish():
    """
    When a genuine document question retrieves relevant chunks,
    relevance grading accepts the chunks, sets retrieval_has_results=True,
    and evaluate_tool_sufficiency returns SUFFICIENT to route directly to finish.
    """
    candidate_docs = [
        {
            "content": "Our return policy allows items to be returned within 30 days.",
            "score": 0.95,
        },
        {"content": "Office address is 123 Main St.", "score": 0.40},
    ]

    mock_tool = MagicMock()
    mock_tool.run.return_value = ToolResult(
        observation="Retrieved 2 candidate docs",
        has_data=True,
        state_updates={
            "retrieval_context": "=== UNTRUSTED DATA ===\n...",
            "retrieval_attempted": True,
            "retrieval_has_results": True,
            "raw_retrieved_docs": candidate_docs,
        },
    )

    # LLM grades chunk [1] as relevant
    mock_llm_response = {
        "content": json.dumps(
            {
                "relevant_indices": [1],
                "reasoning": "Chunk 1 contains the 30-day return policy",
            }
        ),
        "input_tokens": 60,
        "output_tokens": 25,
        "cost_usd": 0.0001,
    }

    state: AgentState = {
        "question": "What is our company refund and return policy?",
        "intent": "SIMPLE_RETRIEVAL",
        "tenant_id": 1,
        "sql_attempted": False,
        "retrieval_attempted": False,
        "retrieval_has_results": False,
        "relevant_docs": [],
        "retrieval_context": None,
        "step_count": 0,
        "action_history": [],
        "observation_history": [],
    }

    with patch(
        "app.agent.nodes.retrieval_node.tool_registry.get", return_value=mock_tool
    ), patch(
        "app.agent.core.relevance_grader.async_call_agent_llm_stream",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = mock_llm_response

        updated_state = await retrieval_node(state)
        combined_state = {**state, **updated_state}

        # 1. State assertions
        assert combined_state["retrieval_has_results"] is True
        assert len(combined_state["relevant_docs"]) == 1
        assert "30 days" in combined_state["retrieval_context"]

        # 2. Sufficiency check assertion
        sufficiency = evaluate_tool_sufficiency(combined_state)
        assert sufficiency == "SUFFICIENT"

        # 3. Router action assertion
        combined_state["last_action"] = "retrieval"
        next_action = route_action(combined_state)
        assert next_action == "finish"


# ── Test 3: Chunks Pass Pre-filter but Fail LLM Grading ───────────────────────
@pytest.mark.asyncio
async def test_chunks_pass_prefilter_but_fail_llm_grading():
    """
    Chunks pass the similarity score floor, but LLM determines they do not answer the question.
    Relevance grader returns is_relevant=False, leading to fallback.
    """
    docs = [
        {"content": "Weather forecast for Seattle is 65F and cloudy.", "score": 0.75},
        {"content": "Top 10 vacation spots in Europe.", "score": 0.70},
    ]

    mock_llm_response = {
        "content": json.dumps(
            {
                "relevant_indices": [],
                "reasoning": "Irrelevant to subscription cancellation",
            }
        ),
        "input_tokens": 40,
        "output_tokens": 15,
        "cost_usd": 0.0001,
    }

    with patch(
        "app.agent.core.relevance_grader.async_call_agent_llm_stream",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = mock_llm_response

        result: GradingResult = await grade_retrieval_relevance(
            question="How do I cancel my enterprise subscription?",
            docs=docs,
            tenant_id=1,
        )

        assert result.is_relevant is False
        assert result.relevant_docs == []
        assert result.pre_filtered_count == 0
        assert mock_llm.called


# ── Test 4: Pre-filter Removes All Chunks (No LLM Call Made) ──────────────────
@pytest.mark.asyncio
async def test_prefilter_removes_all_chunks_skips_llm_call():
    """
    When all chunks have scores below the configured score floor,
    pre_filter_docs filters out all candidates and the LLM grading call is skipped entirely.
    """
    low_score_docs = [
        {"content": "Random noise text 1", "score": 0.05},
        {"content": "Random noise text 2", "score": 0.08},
    ]

    with patch.object(agent_settings, "retrieval_score_floor", 0.20), patch(
        "app.agent.core.relevance_grader.async_call_agent_llm_stream",
        new_callable=AsyncMock,
    ) as mock_llm:

        result: GradingResult = await grade_retrieval_relevance(
            question="Where is our SOC2 compliance document?",
            docs=low_score_docs,
            tenant_id=1,
        )

        # 1. Assert pre-filter eliminated all chunks
        assert result.is_relevant is False
        assert result.relevant_docs == []
        assert result.pre_filtered_count == 2

        # 2. Assert LLM was NOT invoked
        mock_llm.assert_not_called()


# ── Test 5: LLM Grading Raises Exception (Fail-Safe Behavior) ─────────────────
@pytest.mark.asyncio
async def test_llm_grading_exception_fails_safe():
    """
    When the LLM grading call raises a TimeoutError or network exception,
    the grader fails closed (is_relevant=False, degraded=True) rather than failing open.
    The graph falls back gracefully to the SQL path without crashing.
    """
    candidate_docs = [
        {"content": "Some partially related document content", "score": 0.80},
    ]

    with patch(
        "app.agent.core.relevance_grader.async_call_agent_llm_stream",
        side_effect=TimeoutError("LLM timed out"),
    ):
        result: GradingResult = await grade_retrieval_relevance(
            question="Show total invoice count for client X",
            docs=candidate_docs,
            tenant_id=1,
        )

        assert result.is_relevant is False
        assert result.relevant_docs == []
        assert result.degraded is True
        assert "timed out" in (result.degraded_reason or "")

        # Verify fallback routing with this failed result
        test_state: AgentState = {
            "intent": "SIMPLE_RETRIEVAL",
            "retrieval_has_results": result.is_relevant,
            "retrieval_context": None,
            "sql_attempted": False,
            "last_action": "retrieval",
        }

        assert evaluate_tool_sufficiency(test_state) == "INSUFFICIENT"
        assert route_action(test_state) == "sql"
