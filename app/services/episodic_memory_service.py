"""Background writing of compressed episodic-memory summaries."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def write_episode(
    self, session_id: str, turns: list[dict[str, str]], user_id: str, tenant_id: str
) -> str | None:
    try:
        from app.memory.episodic_memory import EpisodicMemory
        from app.memory.summarizer import SessionSummarizer

        summary = SessionSummarizer().summarize(turns, tenant_id)
        episode_id = EpisodicMemory().save_episode(
            session_id, summary, user_id, tenant_id, len(turns)
        )
        logger.info(
            "Episodic memory write completed tenant=%s user=%s episode=%s",
            tenant_id,
            user_id,
            episode_id,
        )
        return episode_id
    except Exception as exc:
        logger.warning("Episodic memory task failed: %s", exc)
        raise self.retry(exc=exc)


def trigger_episode_write(
    session_id: str | None,
    turns: list[dict[str, str]],
    user_id: str | int,
    tenant_id: str | int,
) -> None:
    if not session_id or not turns:
        return
    try:
        write_episode.apply_async(
            args=(session_id, turns, str(user_id), str(tenant_id)),
            queue="logging_queue",
            routing_key="logging",
        )
        logger.info(
            "Queued episodic memory write tenant=%s user=%s session=%s",
            tenant_id,
            user_id,
            session_id,
        )
    except Exception as exc:
        logger.warning("Could not queue episodic memory write: %s", exc)
