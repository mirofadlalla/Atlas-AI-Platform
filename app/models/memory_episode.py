"""Persistent, compressed summaries of a user's conversation sessions."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.models.base import Base
from app.models.uuid import uuid_pk


class MemoryEpisode(Base):
    __tablename__ = "memory_episodes"

    episode_id = uuid_pk()
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    session_id = Column(String, nullable=False, index=True)
    summary = Column(Text, nullable=False)
    raw_turns = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc) + timedelta(days=90),
    )
