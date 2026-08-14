"""Memory read, write, recall, and lazy loader graph nodes for conversational state management."""

import logging

from app.agent.core.state import AgentState
from app.agent.nodes.base import emit_node_status, emit_thought_chunk
from app.memory.episodic_memory import EpisodicMemory
from app.memory.semantic_memory import SemanticMemory
from app.memory.short_term_memory import ConversationTurn, ShortTermMemory
from app.services.episodic_memory_service import trigger_episode_write
from app.services.semantic_memory_service import trigger_semantic_memory_extraction

logger = logging.getLogger(__name__)


async def memory_loader_node(state: AgentState) -> dict:
    """
    Lazy memory loader node.
    Evaluates needs_short_term, needs_semantic, and needs_episodic flags,
    and loads ONLY the requested memory layers.
    """
    await emit_node_status(
        "memory_loader",
        "Memory Loader",
        "Loading required memory layers...",
    )
    update = {}
    tenant_id = state.get("tenant_id", "")
    user_id = state.get("user_id", "")
    session_id = state.get("session_id")
    question = state.get("question", "")

    if state.get("needs_short_term") and session_id:
        history = ShortTermMemory().load(tenant_id, user_id, session_id)
        update["conversation_history"] = history
        await emit_thought_chunk(
            f"[Memory Loader] Loaded {len(history)} short-term turn(s).\n"
        )

    if state.get("needs_semantic"):
        memories = SemanticMemory().recall(question, user_id, tenant_id)
        update["recalled_memories"] = memories
        await emit_thought_chunk(
            f"[Memory Loader] Recalled {len(memories)} semantic memory(ies).\n"
        )

    if state.get("needs_episodic"):
        try:
            summaries = EpisodicMemory().get_recent(
                user_id, tenant_id, exclude_session_id=session_id
            )
            update["episode_context"] = "\n".join(f"- {s}" for s in summaries)
            await emit_thought_chunk(
                f"[Memory Loader] Recalled {len(summaries)} episodic summary(ies).\n"
            )
        except Exception as exc:
            logger.warning("Episodic memory read skipped: %s", exc)
            update["episode_context"] = ""

    return update


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
        "Saving session state & extracting long-term facts...",
    )
    memory = ShortTermMemory()
    args = (
        state.get("tenant_id", ""),
        state.get("user_id", ""),
        state.get("session_id"),
    )
    memory.save(*args, ConversationTurn("user", state.get("question", ""), ""))
    memory.save(*args, ConversationTurn("assistant", state.get("final_answer", ""), ""))
    trigger_semantic_memory_extraction(
        state.get("question", ""),
        state.get("final_answer", ""),
        state.get("user_id", ""),
        state.get("tenant_id", ""),
    )
    trigger_episode_write(
        state.get("session_id"),
        state.get("conversation_history", [])
        + [
            {"role": "user", "content": state.get("question", "")},
            {"role": "assistant", "content": state.get("final_answer", "")},
        ],
        state.get("user_id", ""),
        state.get("tenant_id", ""),
    )
    await emit_thought_chunk(
        "[Memory Write] Session state and long-term memory updates successfully saved.\n"
    )
    return {}
