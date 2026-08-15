"""Memory read, write, recall, and lazy loader graph nodes for conversational state management."""

import logging
import re

from app.agent.core.state import AgentState
from app.agent.nodes.base import emit_node_status, emit_thought_chunk
from app.memory.episodic_memory import EpisodicMemory
from app.memory.semantic_memory import SemanticMemory
from app.memory.short_term_memory import ConversationTurn, ShortTermMemory
from app.services.episodic_memory_service import trigger_episode_write
from app.services.semantic_memory_service import trigger_semantic_memory_extraction

logger = logging.getLogger(__name__)

_IMPORTANT_FACT_PATTERN = re.compile(
    r"\b(my\s+name\s+is|i\s+prefer|my\s+favorite|remember\s+that|i\s+live\s+in|اسمي|أنا\s+أفضل|فضلاً\s+احفظ|تذكر\s+أن)\b",
    re.IGNORECASE,
)


def should_trigger_memory_extraction(
    question: str,
    answer: str,
    turn_count: int,
    session_ended: bool = False,
) -> bool:
    """
    Evaluates whether semantic & episodic extraction background jobs should run.
    Triggers ONLY if:
      - Every 10 user turns (user_turn_count % 10 == 0)
      - OR explicit important user fact detected in question (e.g., 'my name is', 'i prefer')
      - OR session ended
    """
    if session_ended:
        return True
    user_turns = turn_count // 2
    if user_turns > 0 and user_turns % 10 == 0 and (turn_count % 2 == 0):
        return True
    if _IMPORTANT_FACT_PATTERN.search(question):
        return True
    return False


async def memory_read_node(state: AgentState) -> dict:
    await emit_node_status(
        "memory_read",
        "Short-Term Memory",
        "Loading session conversation history...",
    )
    history = ShortTermMemory().load(
        state.get("tenant_id", ""), state.get("user_id", ""), state.get("session_id")
    )
    await emit_thought_chunk(
        f"[Short-Term Memory] Loaded {len(history)} past turn(s) for session {state.get('session_id') or 'default'}.\n"
    )
    return {"conversation_history": history}


async def semantic_recall_node(state: AgentState) -> dict:
    await emit_node_status(
        "semantic_recall",
        "Semantic Memory",
        "Searching long-term facts & preferences...",
    )
    memories = SemanticMemory().recall(
        state.get("question", ""), state.get("user_id", ""), state.get("tenant_id", "")
    )
    await emit_thought_chunk(
        f"[Semantic Memory] Found {len(memories)} relevant fact(s) for user {state.get('user_id') or 'anonymous'}.\n"
    )
    return {"recalled_memories": memories}


async def episodic_recall_node(state: AgentState) -> dict:
    await emit_node_status(
        "episodic_recall",
        "Episodic Memory",
        "Recalling recent session summaries...",
    )
    try:
        summaries = EpisodicMemory().get_recent(
            state.get("user_id", ""),
            state.get("tenant_id", ""),
            exclude_session_id=state.get("session_id"),
        )
    except Exception as exc:
        logger.warning("Episodic memory error: %s", exc)
        summaries = []

    await emit_thought_chunk(
        f"[Episodic Memory] Recalled {len(summaries)} recent session summary(ies).\n"
    )
    return {"episode_context": "\n".join(f"- {summary}" for summary in summaries)}


async def memory_write_node(state: AgentState) -> dict:
    await emit_node_status(
        "memory_write",
        "Persisting Memory",
        "Saving short-term conversation turn...",
    )
    memory = ShortTermMemory()
    tenant_id = state.get("tenant_id", "")
    user_id = state.get("user_id", "")
    session_id = state.get("session_id")
    args = (tenant_id, user_id, session_id)

    question = state.get("question", "")
    # Use explicit None check — an empty string is also considered no answer.
    answer = state.get("final_answer") or ""

    # Always save the user turn so the question is recorded in history even on
    # degraded runs.  Without this, the conversation history would have gaps.
    memory.save(*args, ConversationTurn("user", question, ""))

    if answer:
        memory.save(*args, ConversationTurn("assistant", answer, ""))
    else:
        # Skip the empty assistant turn to avoid polluting future context windows
        # with blank turns.  This happens when the agent degrades before
        # finish_node runs and final_answer was never set.
        logger.warning(
            "memory_write: skipping empty assistant turn for tenant=%s session=%s "
            "(agent degraded before finish_node — final_answer is None/empty)",
            tenant_id,
            session_id,
        )

    history = memory.load(*args)
    turn_count = len(history)
    session_ended = bool(state.get("session_ended", False))

    if should_trigger_memory_extraction(question, answer, turn_count, session_ended):
        await emit_thought_chunk(
            "[Memory Write] Milestone reached -> Triggering background semantic fact & episodic summary extraction.\n"
        )
        trigger_semantic_memory_extraction(
            question,
            answer,
            user_id,
            tenant_id,
        )
        trigger_episode_write(
            session_id,
            state.get("conversation_history", [])
            + [
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ],
            user_id,
            tenant_id,
        )
    else:
        await emit_thought_chunk(
            "[Memory Write] Short-term turn saved to Redis. (Background extraction deferred to milestone/fact trigger).\n"
        )

    return {}
