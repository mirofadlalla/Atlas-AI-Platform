"""Database operations for episodic memory."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.memory_episode import MemoryEpisode
from app.core.config import settings


class EpisodeRepository:
    def __init__(self, db: Session):
        self.db = db

    def save_episode(
        self, session_id: str, summary: str, user_id: str, tenant_id: str, raw_turns: int, ttl_days: int | None = None
    ) -> MemoryEpisode:
        now = datetime.now(timezone.utc)
        ttl_days = ttl_days or settings.episodic_memory_ttl_days
        episode = (
            self.db.query(MemoryEpisode)
            .filter(
                MemoryEpisode.session_id == session_id,
                MemoryEpisode.user_id == user_id,
                MemoryEpisode.tenant_id == tenant_id,
            )
            .order_by(MemoryEpisode.created_at.desc())
            .first()
        )
        if episode:
            episode.summary = summary
            episode.raw_turns = raw_turns
            episode.expires_at = now + timedelta(days=ttl_days)
        else:
            episode = MemoryEpisode(
                session_id=session_id,
                summary=summary,
                user_id=user_id,
                tenant_id=tenant_id,
                raw_turns=raw_turns,
                expires_at=now + timedelta(days=ttl_days),
            )
            self.db.add(episode)
        self.db.commit()
        self.db.refresh(episode)
        return episode

    def get_recent(
        self, user_id: str, tenant_id: str, limit: int | None = None, exclude_session_id: str | None = None
    ) -> list[MemoryEpisode]:
        now = datetime.now(timezone.utc)
        query = (
            self.db.query(MemoryEpisode)
            .filter(
                MemoryEpisode.user_id == user_id,
                MemoryEpisode.tenant_id == tenant_id,
                MemoryEpisode.expires_at > now,
            )
        )
        if exclude_session_id:
            query = query.filter(MemoryEpisode.session_id != exclude_session_id)
        return query.order_by(MemoryEpisode.created_at.desc()).limit(limit or settings.episodic_memory_recent_limit).all()
