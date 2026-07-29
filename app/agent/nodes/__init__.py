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
from app.agent.observability.tracing import trace_span
from app.agent.prompts.registry import prompt_registry
from app.agent.schemas import ActionDecision
from app.agent.tools.base import tool_registry
from app.agent.tools.retrieval_tool import RetrievalTool
from app.agent.tools.sql_tool import SQLTool
from app.agent.utils.classification import classify_question_type
from app.agent.utils.llm import call_agent_llm, llm_usage_updates
from app.agent.utils.parsing import extract_first_json_block
from app.agent.utils.retry import with_retry
from app.agent.utils.state_helpers import (
    budget_exceeded_update,
    get_current_question,
)
from app.agent.utils.state_transitions import (
    build_subquestion_answer_update,
    is_single_subquestion,
    should_synthesize_final,
)

logger = logging.getLogger(__name__)

tool_registry.register(SQLTool())
tool_registry.register(RetrievalTool())


def _apply_tool_result(state: AgentState, result, tool_name: str) -> dict:
    history = state.get("observation_history", [])
    obs_record = result.to_observation_record(tool_name)
    tool_observations = list(state.get("tool_observations", []))
    tool_observations.append(
        {
            "tool": obs_record.tool,
            "observation": obs_record.observation[:500],
            "has_data": obs_record.has_data,
        }
    )
    return {
        "observation": result.observation,
        "observation_history": history + [result.observation],
        "tool_observations": tool_observations,
        **result.state_updates,
    }


async def _run_node(name: str, state: AgentState, fn):
    start = time.time()
    status = "success"
    with trace_span(
        name,
        run_id=state.get("run_id"),
        tenant_id=state.get("tenant_id"),
    ):
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
        prompt = prompt_registry.decompose(question)
        try:
            response_dict = await asyncio.to_thread(
                with_retry,
                call_agent_llm,
                prompt,
                "routing",
                s.get("tenant_id"),
            )
            parsed = json.loads(extract_first_json_block(response_dict["content"]))
            sub_questions = parsed.get("sub_questions") or [question]
        except Exception as exc:
            logger.error("Decompose failed: %s", exc)
            sub_questions = [question]
            response_dict = {}

        if not sub_questions:
            sub_questions = [question]

        degraded = False
        degraded_reason = None
        if len(sub_questions) > agent_settings.max_subquestions:
            sub_questions = sub_questions[: agent_settings.max_subquestions]
            degraded = True
            degraded_reason = f"Trimmed to {agent_settings.max_subquestions} sub-questions"

        update = {
            "original_question": question,
            "sub_questions": sub_questions,
            "current_sub_question_index": 0,
            "sub_answers": [],
            "degraded": degraded,
            "degraded_reason": degraded_reason,
            "observation_history": s.get("observation_history", [])
            + [f"Decomposed into {len(sub_questions)} sub-question(s)"],
        }
        if response_dict:
            update.update(llm_usage_updates(response_dict, s))

        log_node_event(logger, s, "decompose", "completed", parts=len(sub_questions))
        return update

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

        prompt = prompt_registry.thought(
            current_question,
            s.get("step_count", 0),
            actions_context,
            guidance,
        )
        try:
            response = await asyncio.to_thread(
                with_retry,
                call_agent_llm,
                prompt,
                "routing",
                s.get("tenant_id"),
            )
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
                "action_history": s.get("action_history", []) + [next_action],
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
            "action_history": s.get("action_history", []) + [next_action],
            "observation_history": s.get("observation_history", [])
            + [f"Decision = {next_action}"],
            **llm_usage_updates(response, s),
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
        update = _apply_tool_result(s, result, "sql")
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
        update = _apply_tool_result(s, result, "retrieval")
        log_node_event(logger, s, "retrieval_tool", "completed", has_data=result.has_data)
        return update

    return await _run_node("retrieval_tool", state, _inner)


async def finish_node(state: AgentState):
    async def _inner(s: AgentState):
        try:
            sub_answer_text, data_sources, llm_result = await asyncio.to_thread(
                answer_subquestion, s
            )
            next_state = build_subquestion_answer_update(s, sub_answer_text, data_sources)
            next_state.update(llm_usage_updates(llm_result, s))

            if should_synthesize_final(s):
                if is_single_subquestion(s):
                    next_state["final_answer"] = sub_answer_text
                else:
                    original = s.get("original_question", s.get("question", ""))
                    final, synth_result = await asyncio.to_thread(
                        synthesize_final_answer,
                        original,
                        next_state["sub_answers"],
                        s.get("tenant_id"),
                    )
                    next_state["final_answer"] = final
                    next_state.update(llm_usage_updates(synth_result, {**s, **next_state}))

            log_node_event(
                logger,
                s,
                "finish",
                "completed",
                part=s.get("current_sub_question_index", 0) + 1,
            )
            return next_state
        except Exception as exc:
            logger.error("Finish node failed: %s", exc)
            return {
                "final_answer": f"I encountered an error while generating the answer: {exc}",
                "degraded": True,
                "degraded_reason": "Answer generation failed",
            }

    return await _run_node("finish", state, _inner)
