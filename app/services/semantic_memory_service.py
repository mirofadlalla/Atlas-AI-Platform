"""Asynchronous semantic-memory extraction after a completed response."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def extract_semantic_memory(self, question: str, answer: str, user_id: str, tenant_id: str) -> list[str]:
    try:
        # Import only in the worker task.  The extractor uses agent LLM helpers,
        # whose package initialization builds the agent graph; importing it at
        # module load time creates a route → task → agent → task cycle.
        from app.memory.memory_extractor import MemoryExtractor

        return MemoryExtractor().extract_and_store(question, answer, user_id, tenant_id)
    except Exception as exc:
        logger.warning("Semantic memory task failed: %s", exc)
        raise self.retry(exc=exc)


def trigger_semantic_memory_extraction(question: str, answer: str, user_id: str | int, tenant_id: str | int) -> None:
    """Dispatch extraction without adding latency to the user response."""
    if not question.strip() or not answer.strip():
        return
    try:
        extract_semantic_memory.apply_async(
            args=(question, answer, str(user_id), str(tenant_id)),
            queue="logging_queue",
            routing_key="logging",
        )
    except Exception as exc:
        logger.warning("Could not queue semantic memory extraction: %s", exc)
