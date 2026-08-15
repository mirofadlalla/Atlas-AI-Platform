"""
Fast Hybrid Router and Deterministic Sufficiency Evaluator.

Implements a 2-stage Hybrid Router:
  Stage 1: Pure Deterministic Heuristics (Weighted Keyword Scoring Engine, 0 LLM Calls)
  Stage 2: Fallback LLM Intent Classifier (Invoked ONLY if Stage 1 is ambiguous)

The Intent Router is strictly responsible for routing (intent classification).
Context management is decoupled into MemoryManager.
"""

from __future__ import annotations

import json
import logging

from app.agent.core.config import agent_settings
from app.agent.core.intent_regex_pattern import calculate_deterministic_route
from app.agent.core.state import AgentState
from app.agent.nodes.base import emit_node_status, emit_thought_chunk
from app.agent.tools.base import tool_registry
from app.agent.utils.llm import async_call_agent_llm_stream
from app.agent.utils.parsing import extract_first_json_block

logger = logging.getLogger(__name__)


def _extract_action_history(state: AgentState) -> list[str]:
    stored = state.get("action_history")
    if stored:
        return list(stored)

    actions: list[str] = []
    for obs in state.get("observation_history", []):
        if obs.startswith("Decision = "):
            action = obs.replace("Decision = ", "").split(" ")[0].strip()
            if action:
                actions.append(action)
    return actions


def _detect_action_loop(actions: list[str]) -> bool:
    window = agent_settings.loop_detection_window
    recent = actions[-window:]
    if len(recent) >= 2 and recent[-1] == recent[-2]:
        return True

    if len(recent) >= 4:
        a, b, c, d = recent[-4], recent[-3], recent[-2], recent[-1]
        if a == c and b == d and a != b:
            return True

    if len(recent) >= 6:
        pattern = recent[-3:]
        prev = recent[-6:-3]
        if pattern == prev:
            return True

    return False


async def fast_hybrid_router(state: AgentState) -> dict:
    """
    Classify query intent using Weighted Scoring (Stage 1) or Fallback LLM Classifier (Stage 2).
    """
    question = state.get("question", "").strip()
    tenant_id = state.get("tenant_id")

    await emit_node_status("fast_router", "Hybrid Router", "Analyzing query intent...")

    det_route = calculate_deterministic_route(question)

    if det_route == "GREETING":
        await emit_thought_chunk("[Router] Direct greeting match -> GREETING path.\n")
        return {
            "intent": "GREETING",
            "direct_response": "Hello! I am your AI assistant. How can I help you today?",
        }

    if det_route == "OBVIOUS_SQL":
        await emit_thought_chunk(
            "[Router] High-confidence weighted scoring match -> SIMPLE_SQL path.\n"
        )
        return {
            "intent": "SIMPLE_SQL",
            "direct_response": None,
        }

    if det_route == "OBVIOUS_RETRIEVAL":
        await emit_thought_chunk(
            "[Router] High-confidence weighted scoring match -> SIMPLE_RETRIEVAL path.\n"
        )
        return {
            "intent": "SIMPLE_RETRIEVAL",
            "direct_response": None,
        }

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

    return {
        "intent": intent,
        "direct_response": None,
    }


def route_target_path(state: AgentState) -> str:
    """Map state intent directly to target processing node."""
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
    intent = state.get("intent", "DIRECT_QA")

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
    last_action = state.get("last_action", "finish")
    step_count = state.get("step_count", 0)

    if state.get("degraded") or step_count >= agent_settings.max_steps_per_subquestion:
        return "finish"

    if last_action not in tool_registry.list_tools() + ["finish"]:
        return "finish"

    if _detect_action_loop(_extract_action_history(state)):
        logger.info("Action loop detected → finish")
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
