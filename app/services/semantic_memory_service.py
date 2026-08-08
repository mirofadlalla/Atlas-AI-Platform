"""Asynchronous semantic-memory extraction after a completed response."""

from __future__ import annotations

import logging

from celery import shared_task

from app.core.config import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def extract_semantic_memory(
    self, question: str, answer: str, user_id: str, tenant_id: str
) -> list[str]:
    try:
        # Import only in the worker task.  The extractor uses agent LLM helpers,
        # whose package initialization builds the agent graph; importing it at
        # module load time creates a route → task → agent → task cycle.
        from app.memory.memory_extractor import MemoryExtractor

        memory_ids = MemoryExtractor().extract_and_store(
            question, answer, user_id, tenant_id
        )
        logger.info(
            "Semantic memory extraction completed tenant=%s user=%s stored=%s",
            tenant_id,
            user_id,
            len(memory_ids),
        )
        return memory_ids
    except Exception as exc:
        logger.warning("Semantic memory task failed: %s", exc)
        raise self.retry(exc=exc)


def trigger_semantic_memory_extraction(
    question: str, answer: str, user_id: str | int, tenant_id: str | int
) -> None:
    """Dispatch extraction without adding latency to the user response."""
    if not question.strip() or not answer.strip():
        return
    try:
        extract_semantic_memory.apply_async(
            args=(question, answer, str(user_id), str(tenant_id)),
            queue="logging_queue",
            routing_key="logging",
        )
        logger.info(
            "Queued semantic memory extraction tenant=%s user=%s", tenant_id, user_id
        )
    except Exception as exc:
        logger.warning("Could not queue semantic memory extraction: %s", exc)


@shared_task
def prune_low_importance_semantic_memories() -> bool:
    """Nightly maintenance task for low-value long-term memories."""
    from app.memory.semantic_memory import SemanticMemory

    success = SemanticMemory().prune_low_importance(
        settings.semantic_memory_prune_importance_below
    )
    logger.info("Semantic memory prune completed success=%s", success)
    return success
