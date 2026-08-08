"""Read and write compressed cross-session conversation episodes."""

from __future__ import annotations

import logging

from app.core.db import get_db_session
from app.repositories.episode_repository import EpisodeRepository

logger = logging.getLogger(__name__)


class EpisodicMemory:
    def save_episode(
        self,
        session_id: str | None,
        summary: str,
        user_id: str | int,
        tenant_id: str | int,
        raw_turns: int,
    ) -> str | None:
        if not session_id or not summary.strip():
            return None
        try:
            with get_db_session() as db:
                episode = EpisodeRepository(db).save_episode(
                    session_id, summary, str(user_id), str(tenant_id), raw_turns
                )
            logger.info(
                "Saved episodic memory id=%s tenant=%s user=%s",
                episode.episode_id,
                tenant_id,
                user_id,
            )
            return episode.episode_id
        except Exception as exc:
            logger.warning("Episodic memory write failed: %s", exc)
            return None

    def get_recent(
        self,
        user_id: str | int,
        tenant_id: str | int,
        limit: int | None = None,
        exclude_session_id: str | None = None,
    ) -> list[str]:
        try:
            with get_db_session() as db:
                episodes = EpisodeRepository(db).get_recent(
                    str(user_id), str(tenant_id), limit, exclude_session_id
                )
                return [episode.summary for episode in episodes]
        except Exception as exc:
            logger.warning("Episodic memory read failed: %s", exc)
            return []

    def clear_user(self, user_id: str | int, tenant_id: str | int) -> int:
        try:
            with get_db_session() as db:
                return EpisodeRepository(db).clear_user(str(user_id), str(tenant_id))
        except Exception as exc:
            logger.warning("Episodic memory clear failed: %s", exc)
            return 0
