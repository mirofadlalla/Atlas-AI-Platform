"""Optional Redis-backed idempotency for completed agent runs."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agent.core.config import agent_settings
from app.core.config import settings

logger = logging.getLogger(__name__)


def _run_key(tenant_id: str, run_id: str) -> str:
    """
    Build a tenant-scoped Redis key for completed run results.

    Including tenant_id prevents cross-tenant cache collisions if a run_id
    is accidentally reused across tenants (e.g. during retry logic).
    """
    return f"agent:run:complete:{tenant_id}:{run_id}"


def get_cached_run_result(
    run_id: str,
    tenant_id: str,
) -> dict[str, Any] | None:
    if not agent_settings.run_idempotency_enabled:
        return None
    try:
        import redis

        client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        raw = client.get(_run_key(tenant_id, run_id))
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.debug("Run idempotency cache unavailable: %s", exc)
    return None


def cache_run_result(
    run_id: str,
    tenant_id: str,
    result: dict[str, Any],
) -> None:
    if not agent_settings.run_idempotency_enabled:
        return
    try:
        import redis

        client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.setex(
            _run_key(tenant_id, run_id),
            agent_settings.run_idempotency_ttl_seconds,
            json.dumps(result),
        )
    except Exception as exc:
        logger.debug("Could not cache run result: %s", exc)
