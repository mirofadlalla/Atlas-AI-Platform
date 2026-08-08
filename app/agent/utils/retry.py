"""Retry wrapper for transient LLM/DB failures."""

from __future__ import annotations

import logging
from typing import Callable, TypeVar

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.agent.core.config import agent_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _retryable_exceptions() -> tuple[type[BaseException], ...]:
    """
    Returns a tuple of exception types that are considered retryable.
    """
    excs: list[type[BaseException]] = [ConnectionError, TimeoutError, OSError]
    try:
        from groq import APIConnectionError, RateLimitError  # type: ignore

        excs.extend([APIConnectionError, RateLimitError])
    except ImportError:
        pass
    return tuple(excs)


def with_retry(fn: Callable[..., T], *args, **kwargs) -> T:
    """Execute *fn* with bounded exponential backoff on transient errors."""

    @retry(
        reraise=True,  # Reraise the last exception if all retries fail not to swallow it
        stop=stop_after_attempt(agent_settings.llm_retry_attempts),
        wait=wait_exponential(
            min=agent_settings.llm_retry_min_wait_seconds,
            max=agent_settings.llm_retry_max_wait_seconds,
        ),
        retry=retry_if_exception_type(
            _retryable_exceptions()
        ),  # Retry only on specified transient exceptions
        before_sleep=lambda rs: logger.warning(
            "Retrying %s after %s (attempt %s)",
            getattr(fn, "__name__", fn),
            rs.outcome.exception() if rs.outcome else "unknown",
            rs.attempt_number,
        ),
    )
    def _wrapped() -> T:
        return fn(*args, **kwargs)

    return _wrapped()


# before_sleep
# before_sleep=lambda rs:
# كل مرة قبل ما ينام
# يشغل Lambda.
# الـ
# rs
# هو Retry State.
# فيه معلومات عن المحاولة.
# ثم
# logger.warning(
# يطبع Warning.
# Retrying %s
# اسم الدالة.
# after %s
# سبب الخطأ.
# attempt %s
# رقم المحاولة.
# مثلاً
# Retrying generate_answer
# after TimeoutError
# attempt 2
