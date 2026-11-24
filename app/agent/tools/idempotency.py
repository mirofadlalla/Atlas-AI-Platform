"""Tool idempotency guard: key derivation, Redis locking, and result caching."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.tools.base import ToolResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level lazy Redis client
# ---------------------------------------------------------------------------
_redis_client = None


def get_redis_client():
    """Return a cached module-level lazy Redis client using settings.REDIS_URL."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    try:
        import redis  # type: ignore

        from app.core.config import settings

        _redis_client = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        return _redis_client
    except ImportError:
        logger.warning(
            "redis package is not installed; tool idempotency cache is disabled."
        )
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to create Redis client for idempotency: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


def build_key(tool_name: str, tenant_id: str, run_id: str, input_dict: dict) -> str:
    """Return full 64-char SHA-256 hex digest for the given inputs.

    Redis key prefix: atlas:idem:{hex}
    """
    raw = f"{tool_name}|{tenant_id}|{run_id}|{sorted(input_dict.items())}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def fetch_cached_result(key: str):
    """GET from Redis at atlas:idem:{key}.

    Returns a :class:`ToolResult` on hit, or None on miss / error.
    """
    try:
        from app.agent.tools.base import ToolResult

        client = get_redis_client()
        if client is None:
            return None

        raw = client.get(f"atlas:idem:{key}")
        if raw is None:
            return None

        data = json.loads(raw)
        return ToolResult(
            observation=data.get("observation", ""),
            has_data=data.get("has_data", False),
            state_updates=data.get("state_updates", {}),
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("fetch_cached_result error (key=%s): %s", key[:12], exc)
        return None


def cache_tool_result(key: str, result, ttl: int) -> None:
    """Serialize *result* to JSON and SETEX in Redis with the given *ttl*.

    Silently swallows all exceptions (logs at DEBUG).
    """
    try:
        client = get_redis_client()
        if client is None:
            return

        payload = json.dumps(dataclasses.asdict(result))
        client.setex(f"atlas:idem:{key}", ttl, payload)
    except Exception as exc:  # noqa: BLE001
        logger.debug("cache_tool_result error (key=%s): %s", key[:12], exc)


# ---------------------------------------------------------------------------
# Lock helpers
# ---------------------------------------------------------------------------


def acquire_lock(key: str, ttl: int = 30) -> bool:
    """SET atlas:lock:{key} 1 NX EX ttl.

    Returns True if the lock was acquired, False otherwise.
    """
    try:
        client = get_redis_client()
        if client is None:
            # No Redis → behave as if lock was acquired so execution proceeds.
            return True

        result = client.set(f"atlas:lock:{key}", "1", nx=True, ex=ttl)
        return result is True
    except Exception as exc:  # noqa: BLE001
        logger.debug("acquire_lock error (key=%s): %s", key[:12], exc)
        # Fail open: allow execution to proceed.
        return True


def release_lock(key: str) -> None:
    """DEL atlas:lock:{key}.

    Silently swallows all exceptions.
    """
    try:
        client = get_redis_client()
        if client is None:
            return
        client.delete(f"atlas:lock:{key}")
    except Exception as exc:  # noqa: BLE001
        logger.debug("release_lock error (key=%s): %s", key[:12], exc)
