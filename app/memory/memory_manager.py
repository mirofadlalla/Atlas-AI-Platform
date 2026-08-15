"""
Unified MemoryManager with Session-Level Caching and Parallel Context Enrichment.

Decouples memory context management from intent routing.
Short-Term Memory is loaded live on every turn from Redis.
Semantic & Episodic Memories are loaded ONCE at session start (Turn 1), cached in Redis for the session,
and reused across all subsequent turns of the same session without hitting Qdrant/DB on every turn.
"""

from __future__ import annotations

import asyncio
import json
import logging

from app.core.config import settings
from app.memory.episodic_memory import EpisodicMemory
from app.memory.semantic_memory import SemanticMemory
from app.memory.short_term_memory import ShortTermMemory

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Decoupled Memory Manager for fast context loading.
    - Short-Term Memory: Loaded live on every turn from Redis (0 LLM calls, ~1ms).
    - Semantic & Episodic Memory: Loaded ONCE per session, cached in Redis, 0 Qdrant queries on turns 2+.
    """

    def __init__(self):
        self.short_term = ShortTermMemory()
        self.semantic = SemanticMemory()
        self.episodic = EpisodicMemory()

    @staticmethod
    def _redis_client():
        import redis

        return redis.from_url(settings.REDIS_URL, decode_responses=True)

    @staticmethod
    def session_cache_key(tenant_id: str, user_id: str, session_id: str | None) -> str:
        s_id = session_id or "default"
        return f"atlas:session_memory:{tenant_id}:{user_id}:{s_id}"

    async def load_fast_context(
        self, tenant_id: str, user_id: str, session_id: str | None, question: str
    ) -> dict:
        """
        Load short-term history live, and fetch semantic/episodic context from session cache.
        On Turn 1 (Cache Miss), queries Qdrant/DB once and populates the session cache.
        """

        # 1. Short-Term Memory: ALWAYS live read per turn
        async def _load_st():
            if not session_id:
                return []
            return await asyncio.to_thread(
                self.short_term.load, tenant_id, user_id, session_id
            )

        # 2. Semantic & Episodic Memory: Loaded ONCE per session (Session-level Cache)
        async def _load_session_memories():
            if not user_id:
                return [], ""

            cache_key = self.session_cache_key(tenant_id, user_id, session_id)
            try:
                r = self._redis_client()
                cached_raw = r.get(cache_key)
                if cached_raw:
                    data = json.loads(cached_raw)
                    logger.info(
                        "Session memory cache HIT tenant=%s user=%s session=%s",
                        tenant_id,
                        user_id,
                        session_id or "default",
                    )
                    return data.get("recalled_memories", []), data.get(
                        "episode_context", ""
                    )
            except Exception as exc:
                logger.debug("Session memory cache read failed: %s", exc)

            # Cache Miss -> Load from Qdrant and Episodic DB once
            logger.info(
                "Session memory cache MISS -> Querying Qdrant & Episodic DB for session=%s",
                session_id or "default",
            )
            memories = await asyncio.to_thread(
                self.semantic.recall, question, user_id, tenant_id
            )
            try:
                summaries = await asyncio.to_thread(
                    self.episodic.get_recent,
                    user_id,
                    tenant_id,
                    exclude_session_id=session_id,
                )
                episode_ctx = (
                    "\n".join(f"- {s}" for s in summaries) if summaries else ""
                )
            except Exception as exc:
                logger.warning("Episodic memory read error: %s", exc)
                episode_ctx = ""

            # Cache in Redis for 1 hour (3600s)
            try:
                r = self._redis_client()
                r.setex(
                    cache_key,
                    3600,
                    json.dumps(
                        {
                            "recalled_memories": memories,
                            "episode_context": episode_ctx,
                        }
                    ),
                )
            except Exception as exc:
                logger.debug("Session memory cache write failed: %s", exc)

            return memories, episode_ctx

        history, (memories, episode_ctx) = await asyncio.gather(
            _load_st(), _load_session_memories()
        )
        return {
            "conversation_history": history,
            "recalled_memories": memories,
            "episode_context": episode_ctx,
        }

    def invalidate_session_cache(
        self, tenant_id: str, user_id: str, session_id: str | None
    ) -> None:
        """Invalidate cached session memories when new facts/episodes are extracted."""
        try:
            cache_key = self.session_cache_key(tenant_id, user_id, session_id)
            self._redis_client().delete(cache_key)
            logger.info("Invalidated session memory cache key=%s", cache_key)
        except Exception as exc:
            logger.debug("Session memory cache invalidation failed: %s", exc)


memory_manager = MemoryManager()
