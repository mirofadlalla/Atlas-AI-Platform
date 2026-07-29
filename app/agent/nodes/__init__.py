"""Async graph node wrappers with observability and budget guards."""

from __future__ import annotations

import asyncio
import json
import logging
import time

from app.agent.core.config import agent_settings
from app.agent.core.state import AgentState
from app.agent.nodes.finish_helpers import answer_subquestion, synthesize_final_answer
from app.agent.observability.logging import log_node_event
from app.agent.observability.metrics import (
    agent_node_duration_seconds,
    agent_node_executions_total,
    agent_sql_rows_returned,
)
from app.agent.schemas import ActionDecision, format_instructions
from app.agent.tools.base import tool_registry
from app.agent.tools.retrieval_tool import RetrievalTool
from app.agent.tools.sql_tool import SQLTool
from app.agent.utils.classification import classify_question_type
from app.agent.utils.parsing import extract_first_json_block
from app.agent.utils.retry import with_retry
from app.agent.utils.state_helpers import (
    append_sub_answer,
    budget_exceeded_update,
    get_current_question,
    per_subquestion_reset,
)
from app.services.llm_runner import call_llama

logger = logging.getLogger(__name__)

tool_registry.register(SQLTool())
tool_registry.register(RetrievalTool())


def _apply_tool_result(state: AgentState, result) -> dict:
    history = state.get("observation_history", [])
    update = {
        "observation": result.observation,
        "observation_history": history + [result.observation],
        **result.state_updates,
    }
    return update


async def _run_node(name: str, state: AgentState, fn):
    start = time.time()
    status = "success"
    try:
        if budget := budget_exceeded_update(state):
            return budget
        result = await fn(state)
        return result
    except Exception as exc:
        status = "error"
        logger.error("%s node failed: %s", name, exc, exc_info=True)
        raise
    finally:
        agent_node_executions_total.labels(node=name, status=status).inc()
        agent_node_duration_seconds.labels(node=name).observe(time.time() - start)


async def decompose_node(state: AgentState):
    async def _inner(s: AgentState):
        question = s.get("question", "")
        prompt = f"""You are an AI planner for an Enterprise RAG and Database system.
Analyze whether the question is compound and must be split into sub-questions.

Return ONLY JSON:
{{"is_compound": true/false, "sub_questions": ["...", "..."]}}

Question: "{question}"
"""
        try:
            response_dict = await asyncio.to_thread(with_retry, call_llama, prompt)
            parsed = json.loads(extract_first_json_block(response_dict["content"]))
            sub_questions = parsed.get("sub_questions") or [question]
        except Exception as exc:
            logger.error("Decompose failed: %s", exc)
            sub_questions = [question]

        if not sub_questions:
            sub_questions = [question]

        degraded = False
        degraded_reason = None
        if len(sub_questions) > agent_settings.max_subquestions:
            sub_questions = sub_questions[: agent_settings.max_subquestions]
            degraded = True
            degraded_reason = f"Trimmed to {agent_settings.max_subquestions} sub-questions"

        log_node_event(logger, s, "decompose", "completed", parts=len(sub_questions))
        return {
            "original_question": question,
            "sub_questions": sub_questions,
            "current_sub_question_index": 0,
            "sub_answers": [],
            "degraded": degraded,
            "degraded_reason": degraded_reason,
            "observation_history": s.get("observation_history", [])
            + [f"Decomposed into {len(sub_questions)} sub-question(s)"],
        }

    return await _run_node("decompose", state, _inner)


async def thought_node(state: AgentState):
    async def _inner(s: AgentState):
        has_sql = bool(s.get("last_sql"))
        has_retrieval = bool(s.get("retrieval_context"))
        actions = []
        if has_sql:
            actions.append("SQL already executed")
        if has_retrieval:
            actions.append("Retrieval already executed")
        actions_context = "\n".join(actions) if actions else "None"

        current_question = get_current_question(s)
        question_type = classify_question_type(current_question)
        guidance = {
            "data": "Use SQL",
            "knowledge": "Use RETRIEVAL",
        }.get(question_type, "Decide best action")

        prompt = f"""You are an AI agent.

Question: {current_question}
Step: {s.get("step_count", 0)}

Previous actions:
{actions_context}

Guidance: {guidance}

Return ONLY JSON:
{format_instructions}
"""
        try:
            response = await asyncio.to_thread(with_retry, call_llama, prompt)
            next_action = _parse_action_decision(response["content"])
            thought = response["content"]
        except Exception as exc:
            logger.error("Thought node LLM failure: %s", exc)
            next_action = "finish"
            thought = f"LLM error, finishing early: {exc}"
            return {
                "thought": thought,
                "last_action": next_action,
                "step_count": s.get("step_count", 0) + 1,
                "total_step_count": s.get("total_step_count", 0) + 1,
                "degraded": True,
                "degraded_reason": "LLM call failed during reasoning",
                "observation_history": s.get("observation_history", [])
                + [f"Decision = {next_action} (degraded)"],
            }

        step = s.get("step_count", 0) + 1
        total = s.get("total_step_count", 0) + 1
        update: dict = {
            "thought": thought,
            "last_action": next_action,
            "step_count": step,
            "total_step_count": total,
            "observation_history": s.get("observation_history", [])
            + [f"Decision = {next_action}"],
        }
        if step >= agent_settings.max_steps_per_subquestion:
            update["degraded"] = True
            update["degraded_reason"] = "Step limit reached for sub-question"
        return update

    return await _run_node("think", state, _inner)


def _parse_action_decision(response_text: str) -> str:
    try:
        action_decision = ActionDecision.model_validate_json(
            extract_first_json_block(response_text)
        )
        action = action_decision.action.lower().strip()
        if action in tool_registry.list_tools() + ["finish"]:
            return action
    except Exception as exc:
        logger.warning("Could not parse action decision: %s", exc)
    return "finish"


async def sql_node(state: AgentState):
    async def _inner(s: AgentState):
        tool = tool_registry.get("sql")
        assert tool is not None
        result = await asyncio.to_thread(tool.run, s)
        update = _apply_tool_result(s, result)
        if result.has_data:
            agent_sql_rows_returned.observe(1)
        log_node_event(logger, s, "sql_tool", "completed", has_data=result.has_data)
        return update

    return await _run_node("sql_tool", state, _inner)


async def retrieval_node(state: AgentState):
    async def _inner(s: AgentState):
        tool = tool_registry.get("retrieval")
        assert tool is not None
        result = await asyncio.to_thread(tool.run, s)
        update = _apply_tool_result(s, result)
        log_node_event(logger, s, "retrieval_tool", "completed", has_data=result.has_data)
        return update

    return await _run_node("retrieval_tool", state, _inner)


async def finish_node(state: AgentState):
    async def _inner(s: AgentState):
        try:
            sub_questions = s.get("sub_questions") or [s.get("question", "")]
            current_idx = s.get("current_sub_question_index", 0)
            current_question = get_current_question(s)
            is_final_synthesis = current_idx >= len(sub_questions) - 1
            sub_answers = list(s.get("sub_answers", []))

            sub_answer_text, data_sources = await asyncio.to_thread(answer_subquestion, s)
            sub_answers = append_sub_answer(sub_answers, current_question, sub_answer_text)

            next_state = {
                "sub_answers": sub_answers,
                "current_sub_question_index": current_idx + 1,
                **per_subquestion_reset(),
                "observation_history": s.get("observation_history", [])
                + [f"Answered part {current_idx + 1}: {sub_answer_text[:100]}..."],
                "data_sources": data_sources,
            }
            if s.get("degraded"):
                next_state["degraded"] = True
                next_state["degraded_reason"] = s.get("degraded_reason")

            if is_final_synthesis:
                if len(sub_questions) == 1:
                    next_state["final_answer"] = sub_answer_text
                else:
                    original = s.get("original_question", s.get("question", ""))
                    final = await asyncio.to_thread(
                        synthesize_final_answer, original, sub_answers
                    )
                    next_state["final_answer"] = final

            log_node_event(logger, s, "finish", "completed", part=current_idx + 1)
            return next_state
        except Exception as exc:
            logger.error("Finish node failed: %s", exc)
            return {
                "final_answer": f"I encountered an error while generating the answer: {exc}",
                "degraded": True,
                "degraded_reason": "Answer generation failed",
            }

    return await _run_node("finish", state, _inner)
