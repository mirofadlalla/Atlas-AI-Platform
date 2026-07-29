"""Redis-backed retrieval result cache."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.agent.core.config import agent_settings
from app.core.config import settings

logger = logging.getLogger(__name__)


def _cache_key(tenant_id: str | int, question: str) -> str:
    digest = hashlib.sha256(question.strip().lower().encode()).hexdigest()
    return f"agent:retrieval:{tenant_id}:{digest}"


def get_cached_retrieval(tenant_id: str | int, question: str) -> list[dict[str, Any]] | None:
    try:
        import redis

        client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        raw = client.get(_cache_key(tenant_id, question))
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.debug("Retrieval cache miss/unavailable: %s", exc)
    return None


def set_cached_retrieval(
    tenant_id: str | int,
    question: str,
    docs: list[dict[str, Any]],
) -> None:
    try:
        import redis

        client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.setex(
            _cache_key(tenant_id, question),
            agent_settings.retrieval_cache_ttl_seconds,
            json.dumps(docs),
        )
    except Exception as exc:
        logger.debug("Could not write retrieval cache: %s", exc)
