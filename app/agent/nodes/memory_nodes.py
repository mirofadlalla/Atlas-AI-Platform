"""Memory read, write, and recall graph nodes for conversational state management."""

from app.agent.core.state import AgentState
from app.agent.nodes.base import emit_node_status, emit_thought_chunk
from app.memory.episodic_memory import EpisodicMemory
from app.memory.semantic_memory import SemanticMemory
from app.memory.short_term_memory import ConversationTurn, ShortTermMemory
from app.services.episodic_memory_service import trigger_episode_write
from app.services.semantic_memory_service import trigger_semantic_memory_extraction


async def memory_read_node(state: AgentState) -> dict:
    """
    Load short-term session turns before the agent begins planning.

    Args:
        state (AgentState): Current state containing 'tenant_id', 'user_id', and 'session_id'.

    Returns:
        dict: State update dictionary containing 'conversation_history'.

    Example:
        >>> state = {"tenant_id": "tenant-1", "user_id": "usr-123", "session_id": "sess-abc"}
        >>> res = await memory_read_node(state)
        >>> res
        {'conversation_history': [{'role': 'user', 'content': 'Hello'}]}
    """
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
    """
    Recall durable semantic memories (user facts/preferences) relevant to the question.

    Args:
        state (AgentState): Current state containing 'question', 'user_id', and 'tenant_id'.

    Returns:
        dict: State update dictionary containing 'recalled_memories'.

    Example:
        >>> state = {"question": "What is my favorite language?", "user_id": "u1", "tenant_id": "t1"}
        >>> res = await semantic_recall_node(state)
        >>> res
        {'recalled_memories': ['User prefers Python over Java.']}
    """
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
    """
    Load compact summaries from past sessions excluding the active session.

    Args:
        state (AgentState): Current state containing 'user_id', 'tenant_id', and 'session_id'.

    Returns:
        dict: State update dictionary containing formatted 'episode_context'.

    Example:
        >>> state = {"user_id": "u1", "tenant_id": "t1", "session_id": "sess-current"}
        >>> res = await episodic_recall_node(state)
        >>> res
        {'episode_context': '- User discussed database setup in session-101.'}
    """
    await emit_node_status(
        "episodic_recall",
        "Episodic Memory",
        "Recalling recent session summaries...",
    )
    summaries = EpisodicMemory().get_recent(
        state.get("user_id", ""),
        state.get("tenant_id", ""),
        exclude_session_id=state.get("session_id"),
    )
    await emit_thought_chunk(
        f"[Episodic Memory] Recalled {len(summaries)} recent session summary(ies).\n"
    )
    return {"episode_context": "\n".join(f"- {summary}" for summary in summaries)}


async def memory_write_node(state: AgentState) -> dict:
    """
    Persist the completed user/assistant conversation turn and trigger background extraction.

    Args:
        state (AgentState): State containing 'tenant_id', 'user_id', 'session_id',
            'question', 'final_answer', and 'conversation_history'.

    Returns:
        dict: Empty state update dictionary `{}`.

    Example:
        >>> state = {
        ...     "tenant_id": "t1", "user_id": "u1", "session_id": "s1",
        ...     "question": "Who created Python?", "final_answer": "Guido van Rossum",
        ...     "conversation_history": []
        ... }
        >>> res = await memory_write_node(state)
        >>> res
        {}
    """
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
