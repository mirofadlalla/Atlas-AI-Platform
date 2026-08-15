"""
Unified MemoryManager with Redis Caching and Parallel Context Enrichment.

Decouples memory context management from intent routing.
"""

from __future__ import annotations

import asyncio
import logging

from app.memory.episodic_memory import EpisodicMemory
from app.memory.semantic_memory import SemanticMemory
from app.memory.short_term_memory import ShortTermMemory

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Decoupled Memory Manager for fast context loading.
    - Short-Term Memory: Always read from Redis (cheap read, 0 LLM calls).
    - Semantic Memory: Fast vector/cache recall for durable facts.
    - Episodic Memory: On-demand only when requested by Planner or Complex path.
    """

    def __init__(self):
        self.short_term = ShortTermMemory()
        self.semantic = SemanticMemory()
        self.episodic = EpisodicMemory()

    async def load_fast_context(
        self, tenant_id: str, user_id: str, session_id: str | None, question: str
    ) -> dict:
        """
        Load short-term history and semantic memories concurrently in parallel.
        """

        async def _load_st():
            if not session_id:
                return []
            return await asyncio.to_thread(
                self.short_term.load, tenant_id, user_id, session_id
            )

        async def _load_sem():
            if not user_id or not question:
                return []
            return await asyncio.to_thread(
                self.semantic.recall, question, user_id, tenant_id
            )

        history, memories = await asyncio.gather(_load_st(), _load_sem())
        return {
            "conversation_history": history,
            "recalled_memories": memories,
        }

    async def load_episodic_on_demand(
        self, tenant_id: str, user_id: str, session_id: str | None
    ) -> str:
        """Load episodic summary memories on demand for complex reasoning."""
        if not user_id:
            return ""
        try:
            summaries = await asyncio.to_thread(
                self.episodic.get_recent,
                user_id,
                tenant_id,
                exclude_session_id=session_id,
            )
            return "\n".join(f"- {s}" for s in summaries)
        except Exception as exc:
            logger.warning("Episodic memory read error: %s", exc)
            return ""


memory_manager = MemoryManager()
