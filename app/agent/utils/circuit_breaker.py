"""In-process circuit breakers for external dependencies."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 60.0,
        # means after 5 failures, the circuit breaker will open and stay open for 60 seconds before allowing a retry
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self._failures = 0
        self._opened_at: float | None = None # 
        self._lock = threading.Lock()

    def _is_open(self) -> bool: # هل الـ Circuit مقفول الآن؟
        if self._opened_at is None:
            return False
        if time.time() - self._opened_at >= self.recovery_timeout_seconds:
            self._failures = 0
            self._opened_at = None
            logger.info("Circuit breaker %s half-open (recovery elapsed)", self.name)
            return False
        return True

    def call(self, fn: Callable[..., T], *args, **kwargs) -> T:
        with self._lock:
            if self._is_open():
                raise RuntimeError(
                    f"Circuit breaker '{self.name}' is open; dependency temporarily unavailable"
                )

        try:
            result = fn(*args, **kwargs)
        except Exception:
            with self._lock:
                self._failures += 1
                if self._failures >= self.failure_threshold:
                    self._opened_at = time.time()
                    logger.warning(
                        "Circuit breaker %s opened after %s failures",
                        self.name,
                        self._failures,
                    )
            raise

        with self._lock:
            self._failures = 0
            self._opened_at = None
        return result

    def reset(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None


llm_circuit_breaker = CircuitBreaker("llm")
db_circuit_breaker = CircuitBreaker("db")


def configure_breakers() -> None:
    from app.agent.core.config import agent_settings

    for breaker in (llm_circuit_breaker, db_circuit_breaker):
        breaker.failure_threshold = agent_settings.circuit_breaker_failure_threshold
        breaker.recovery_timeout_seconds = agent_settings.circuit_breaker_recovery_seconds


configure_breakers()
