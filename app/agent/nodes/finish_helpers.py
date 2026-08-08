"""Helpers for sub-question answering and final synthesis."""

from __future__ import annotations

import logging

from app.agent.core.config import agent_settings
from app.agent.core.state import AgentState, SubAnswer
from app.agent.prompts.registry import prompt_registry
from app.agent.utils.classification import asks_for_db_data
from app.agent.utils.context_budget import truncate_to_token_budget
from app.agent.utils.guardrails import sanitize_untrusted_block, validate_answer_grounding
from app.agent.utils.llm import call_agent_llm
from app.agent.utils.retry import with_retry
from app.agent.utils.state_helpers import get_current_question

logger = logging.getLogger(__name__)


def _format_history(state: AgentState) -> str:
    return "\n".join(f"{turn.get('role', 'user').title()}: {turn.get('content', '')}" for turn in state.get("conversation_history", []))


def _format_memories(state: AgentState) -> str:
    return "\n".join(f"- {memory}" for memory in state.get("recalled_memories", []))

_DEGRADED_NOTE = (
    "IMPORTANT: Data gathering was incomplete or cut short ({reason}). "
    "Answer only from the provided data and explicitly state any limitations."
)


def build_data_summary(state: AgentState, current_question: str) -> tuple[str, list[str]]:
    data_summary: list[str] = []
    data_sources: list[str] = []

    has_sql_results = state.get("sql_has_results", False)
    has_sql_attempt = state.get("sql_attempted", False)
    has_retrieval = bool(state.get("retrieval_context"))

    if asks_for_db_data(current_question) and has_sql_attempt:
        if has_sql_results and state.get("sql_result"):
            data_summary.append(
                f"=== DATABASE QUERY RESULTS (untrusted data) ===\n"
                f"{sanitize_untrusted_block(state.get('sql_result', ''))}"
            )
            data_sources.append("DATABASE")
        else:
            data_summary.append(
                "=== DATABASE QUERY RESULTS ===\nNo matching records found in database"
            )
            data_sources.append("DATABASE (no results)")
    else:
        if state.get("sql_result"):
            data_summary.append(
                f"=== DATABASE QUERY RESULTS (untrusted data) ===\n"
                f"{sanitize_untrusted_block(state.get('sql_result', ''))}"
            )
            data_sources.append("DATABASE")
        if has_retrieval:
            data_summary.append(
                f"=== RETRIEVED KNOWLEDGE BASE DOCUMENTS ===\n"
                f"{sanitize_untrusted_block(state.get('retrieval_context', ''))}"
            )
            data_sources.append("DOCUMENTS")

    text = "\n\n".join(data_summary) if data_summary else "No data was retrieved"
    text = truncate_to_token_budget(text, agent_settings.prompt_max_tokens // 2)
    return text, data_sources


def answer_subquestion(state: AgentState) -> tuple[str, list[str], dict]:
    current_question = get_current_question(state)
    data_summary_text, data_sources = build_data_summary(state, current_question)

    degraded_note = ""
    if state.get("degraded"):
        reason = state.get("degraded_reason") or "unknown"
        degraded_note = _DEGRADED_NOTE.format(reason=reason) + "\n\n"

    prompt = prompt_registry.answer_subquestion(
        current_question, data_summary_text, degraded_note, _format_history(state), _format_memories(state), state.get("episode_context", "")
    )
    response_dict = with_retry(
        call_agent_llm,
        prompt,
        tier="generation",
        tenant_id=state.get("tenant_id"),
    )
    answer, _ = validate_answer_grounding(
        response_dict["content"].strip(),
        data_summary_text,
    )
    return answer, data_sources, response_dict


def synthesize_final_answer(
    original_question: str,
    sub_answers: list[SubAnswer],
    tenant_id: str | None = None,
) -> tuple[str, dict]:
    combined_text = "\n\n".join(
        [f"Q: {sa['question']}\nA: {sa['answer']}" for sa in sub_answers]
    )
    combined_text = truncate_to_token_budget(
        combined_text, agent_settings.prompt_max_tokens // 2
    )
    prompt = prompt_registry.synthesize_final(original_question, combined_text)
    response_dict = with_retry(
        call_agent_llm,
        prompt,
        tier="generation",
        tenant_id=tenant_id,
    )
    answer, _ = validate_answer_grounding(
        response_dict["content"].strip(),
        combined_text,
    )
    return answer, response_dict
