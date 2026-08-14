"""
Fast Hybrid Router and Deterministic Sufficiency Evaluator.

Implements a 2-stage Hybrid Router:
  Stage 1: Pure Deterministic Heuristics (Regex & Keywords, 0 LLM Calls)
  Stage 2: Fallback LLM Intent Classifier (Invoked ONLY if Stage 1 is ambiguous)

Also provides deterministic sufficiency rules to evaluate tool outputs without LLM calls.
"""

from __future__ import annotations

import json
import logging
import re

from app.agent.core.config import agent_settings
from app.agent.core.state import AgentState
from app.agent.nodes.base import emit_node_status, emit_thought_chunk
from app.agent.tools.base import tool_registry
from app.agent.utils.llm import async_call_agent_llm_stream
from app.agent.utils.parsing import extract_first_json_block

logger = logging.getLogger(__name__)

# Regex Patterns for Stage 1 Deterministic Router
_RE_GREETING = re.compile(
    r"^(hi|hello|hey|good morning|good evening|thanks|thank you|who are you|what can you do)[\s!.]*$",
    re.IGNORECASE,
)

_SQL_KEYWORDS = re.compile(
    r"\b(how many|count of|total number|signed up|active users|table rows|database|sum of|average|list users|show users)\b",
    re.IGNORECASE,
)

_RETRIEVAL_KEYWORDS = re.compile(
    r"\b(policy|documentation|manual|how to|guide|terms|contract|pdf|document|file)\b",
    re.IGNORECASE,
)


def _detect_memory_needs(question: str, session_id: str | None) -> dict[str, bool]:
    """Calculate memory flags based on question content and session presence."""
    q_lower = question.lower()

    # Pronoun / conversational references require short-term memory
    has_conversational_ref = bool(
        re.search(r"\b(it|this|that|they|them|previous|above|before)\b", q_lower)
    )
    needs_short_term = bool(session_id) and has_conversational_ref

    # User profile/preference references require semantic memory
    needs_semantic = bool(
        re.search(r"\b(my|i|favorite|prefer|my name|my role)\b", q_lower)
    )

    # Past session references require episodic memory
    needs_episodic = bool(
        re.search(r"\b(last time|yesterday|past session|earlier chat)\b", q_lower)
    )

    return {
        "needs_short_term": needs_short_term,
        "needs_semantic": needs_semantic,
        "needs_episodic": needs_episodic,
    }


async def fast_hybrid_router(state: AgentState) -> dict:
    """
    Stage 1: Pure Deterministic Check (0 LLM Calls).
    Stage 2: Fallback LLM Classifier (1 Fast LLM Call ONLY if Stage 1 is Ambiguous).
    """
    question = state.get("question", "").strip()
    session_id = state.get("session_id")
    tenant_id = state.get("tenant_id")

    await emit_node_status("fast_router", "Hybrid Router", "Analyzing query intent...")

    # Stage 1: Deterministic Heuristic Engine
    if _RE_GREETING.match(question):
        await emit_thought_chunk("[Router] Direct greeting match -> GREETING path.\n")
        return {
            "intent": "GREETING",
            "needs_short_term": False,
            "needs_semantic": False,
            "needs_episodic": False,
            "direct_response": "Hello! I am your AI assistant. How can I help you today?",
        }

    mem_flags = _detect_memory_needs(question, session_id)

    if _SQL_KEYWORDS.search(question) and not _RETRIEVAL_KEYWORDS.search(question):
        await emit_thought_chunk(
            "[Router] Deterministic metric/SQL match -> SIMPLE_SQL path.\n"
        )
        return {
            "intent": "SIMPLE_SQL",
            "direct_response": None,
            **mem_flags,
        }

    if _RETRIEVAL_KEYWORDS.search(question) and not _SQL_KEYWORDS.search(question):
        await emit_thought_chunk(
            "[Router] Deterministic document match -> SIMPLE_RETRIEVAL path.\n"
        )
        return {
            "intent": "SIMPLE_RETRIEVAL",
            "direct_response": None,
            **mem_flags,
        }

    # Stage 2: Fallback LLM Classifier (For Ambiguous / Unknown Prompts ONLY)
    await emit_thought_chunk(
        "[Router] Ambiguous prompt -> Invoking Fallback Intent Classifier...\n"
    )
    classifier_prompt = (
        f"Classify the following query into ONE intent category:\n"
        f"- DIRECT_QA: General knowledge or conceptual questions.\n"
        f"- SIMPLE_SQL: Single relational database or counting query.\n"
        f"- SIMPLE_RETRIEVAL: Single document or policy lookup.\n"
        f"- COMPLEX: Multi-step, hybrid SQL+Retrieval, or complex analytical query.\n\n"
        f'Query: "{question}"\n\n'
        f'Return JSON: {{"intent": "CATEGORY"}}'
    )

    try:
        response = await async_call_agent_llm_stream(
            prompt=classifier_prompt,
            tier="routing",
            tenant_id=tenant_id,
            event_type="stream_thought_chunk",
        )
        parsed = json.loads(extract_first_json_block(response["content"]))
        intent = parsed.get("intent", "DIRECT_QA").upper()
    except Exception as exc:
        logger.warning("Fallback classifier failed: %s, defaulting to DIRECT_QA", exc)
        intent = "DIRECT_QA"

    if intent == "COMPLEX":
        mem_flags = {
            "needs_short_term": True,
            "needs_semantic": True,
            "needs_episodic": True,
        }

    return {
        "intent": intent,
        "direct_response": None,
        **mem_flags,
    }


# Routing Condition Functions for LangGraph Edges


def route_initial_intent(state: AgentState) -> str:
    """Decide whether to load memory first or go straight to target node."""
    needs_mem = (
        state.get("needs_short_term")
        or state.get("needs_semantic")
        or state.get("needs_episodic")
    )
    if needs_mem:
        return "memory_loader"

    return route_target_path(state)


def route_target_path(state: AgentState) -> str:
    """Map state intent directly to target processing node (No Router Re-evaluation)."""
    intent = state.get("intent", "DIRECT_QA")
    if intent in ("GREETING", "DIRECT_QA"):
        return "direct_answer"
    elif intent == "SIMPLE_SQL":
        return "sql_tool"
    elif intent == "SIMPLE_RETRIEVAL":
        return "retrieval_tool"
    elif intent == "COMPLEX":
        return "decompose"
    return "direct_answer"


def evaluate_tool_sufficiency(state: AgentState) -> str:
    """
    Deterministic Sufficiency Evaluator (Python Code Only — 0 LLM Calls).
    Determines if single-pass tool output is sufficient to jump to synthesis.
    """
    intent = state.get("intent", "DIRECT_QA")

    # If in multi-step complex mode, pass to agent planner
    if intent == "COMPLEX":
        return "INSUFFICIENT"

    if intent == "SIMPLE_SQL":
        if state.get("sql_has_results") and not state.get("degraded"):
            return "SUFFICIENT"
        return "INSUFFICIENT"

    if intent == "SIMPLE_RETRIEVAL":
        if state.get("retrieval_has_results") or bool(state.get("retrieval_context")):
            return "SUFFICIENT"
        return "INSUFFICIENT"

    return "SUFFICIENT"


def route_action(state: AgentState) -> str:
    """Agentic Re-Act Planner routing for complex / escalated queries."""
    last_action = state.get("last_action", "finish")
    step_count = state.get("step_count", 0)

    if state.get("degraded") or step_count >= agent_settings.max_steps_per_subquestion:
        return "finish"

    if last_action not in tool_registry.list_tools() + ["finish"]:
        return "finish"

    if last_action == "sql":
        if state.get("sql_has_results"):
            return "finish"
        if state.get("sql_attempted") and not state.get("retrieval_attempted"):
            return "retrieval"
        return "finish"

    if last_action == "retrieval":
        if state.get("retrieval_has_results") or bool(state.get("retrieval_context")):
            return "finish"
        return "finish"

    return last_action


def route_after_finish(state: AgentState) -> str:
    idx = state.get("current_sub_question_index", 0)
    subs = state.get("sub_questions", [])
    if idx < len(subs):
        return "think"
    return "end"
