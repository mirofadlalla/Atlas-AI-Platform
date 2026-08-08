"""Redis-backed, tenant-isolated short-term conversation memory."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConversationTurn:
    role: str
    content: str
    timestamp: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class ShortTermMemory:
    """Stores a bounded history for one tenant/user/browser session.

    Redis failures are deliberately non-fatal: memory must never prevent a
    user from receiving an answer.
    """

    def __init__(self, ttl_seconds: int | None = None, max_turns: int | None = None):
        self.ttl_seconds = ttl_seconds or settings.stm_ttl_seconds
        self.max_turns = max_turns or settings.stm_max_turns

    @staticmethod
    def key(tenant_id: str | int, user_id: str | int, session_id: str) -> str:
        return f"atlas:stm:{tenant_id}:{user_id}:{session_id}"

    @staticmethod
    def _client():
        import redis

        return redis.from_url(settings.REDIS_URL, decode_responses=True)

    def load(self, tenant_id: str | int, user_id: str | int, session_id: str | None) -> list[dict[str, str]]:
        if not session_id:
            return []
        try:
            raw = self._client().get(self.key(tenant_id, user_id, session_id))
            if not raw:
                return []
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                return []
            return [turn for turn in parsed if isinstance(turn, dict) and turn.get("role") and turn.get("content")]
        except Exception as exc:
            logger.warning("Short-term memory read failed; continuing without history: %s", exc)
            return []

    def save(self, tenant_id: str | int, user_id: str | int, session_id: str | None, turn: ConversationTurn | dict[str, Any]) -> None:
        if not session_id:
            return
        record = turn.to_dict() if isinstance(turn, ConversationTurn) else dict(turn)
        if not record.get("timestamp"):
            record["timestamp"] = datetime.now(timezone.utc).isoformat()
        if record.get("role") not in {"user", "assistant"} or not str(record.get("content", "")).strip():
            logger.warning("Ignoring invalid short-term memory turn")
            return
        try:
            client = self._client()
            key = self.key(tenant_id, user_id, session_id)
            # A single Redis transaction makes the append + trim + TTL refresh atomic.
            with client.pipeline() as pipe:
                while True:
                    try:
                        pipe.watch(key)
                        raw = pipe.get(key)
                        history = json.loads(raw) if raw else []
                        if not isinstance(history, list):
                            history = []
                        history.append(record)
                        history = history[-self.max_turns :]
                        pipe.multi()
                        pipe.setex(key, self.ttl_seconds, json.dumps(history, ensure_ascii=False))
                        pipe.execute()
                        return
                    except Exception as exc:
                        # WatchError is retried; all other errors keep memory fail-open.
                        if exc.__class__.__name__ == "WatchError":
                            continue
                        raise
        except Exception as exc:
            logger.warning("Short-term memory write failed; answer was not blocked: %s", exc)

    def clear(self, tenant_id: str | int, user_id: str | int, session_id: str | None) -> None:
        if not session_id:
            return
        try:
            self._client().delete(self.key(tenant_id, user_id, session_id))
        except Exception as exc:
            logger.warning("Short-term memory clear failed: %s", exc)

    def clear_all(self, tenant_id: str | int, user_id: str | int) -> int:
        """Clear every active session for one user without touching other users."""
        try:
            client = self._client()
            keys = list(client.scan_iter(match=f"atlas:stm:{tenant_id}:{user_id}:*", count=100))
            return int(client.delete(*keys)) if keys else 0
        except Exception as exc:
            logger.warning("Short-term memory bulk clear failed: %s", exc)
            return 0
