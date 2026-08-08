"""Lightweight tracing spans for agent nodes (stdlib-only, OTEL-compatible shape)."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator

logger = logging.getLogger(__name__)


# الفكرة الأساسية هي إن كل خطوة في الـ Agent (Node) تتلف حوالينها بـ Span، بحيث تعرف:
# بدأت إمتى؟
# انتهت إمتى؟
# استغرقت قد إيه؟
# نجحت ولا فشلت؟
# كانت تخص أي Run؟
# كانت تخص أي Tenant؟

# وده بيساعد جدًا في الـ Debugging والـ Monitoring.
# الفكرة العامة

# تخيل إن عندك Agent بالشكل ده:
# User Question
#       │
#       ▼
# Retrieve Documents
#       │
#       ▼
# Rank Results
#       │
#       ▼
# Generate SQL
#       │
#       ▼
# Execute Query

# كل خطوة من دول اسمها Span.
# ولما كلهم يتجمعوا يبقى عندك Trace كامل.

# مثلاً:
# Trace
# │
# ├── Retrieve
# │      130 ms
# │
# ├── Reranker
# │      40 ms
# │
# ├── SQL Generator
# │      180 ms
# │
# └── Execute
#        20 ms


@dataclass
class Span:
    trace_id: str  # كل الـ Spans الخاصة بنفس الطلب ليها نفس Trace ID.
    span_id: str  # كل Span ليها ID خاص.
    name: str
    start_time: float
    attributes: dict[str, Any] = field(default_factory=dict)
    end_time: float | None = None
    status: str = "ok"

    def finish(self, status: str = "ok") -> None:
        self.end_time = time.time()
        self.status = status
        duration_ms = (self.end_time - self.start_time) * 1000
        logger.info(
            "trace span finished",
            extra={
                "trace": {
                    "trace_id": self.trace_id,
                    "span_id": self.span_id,
                    "name": self.name,
                    "duration_ms": round(duration_ms, 2),
                    "status": status,
                    **self.attributes,
                }
            },
        )


@contextmanager
def trace_span(
    name: str,
    run_id: str | None = None,
    tenant_id: str | None = None,
    **attributes: Any,
) -> Generator[Span, None, None]:
    span = Span(
        trace_id=run_id or str(uuid.uuid4()),
        span_id=str(uuid.uuid4())[:16],
        name=name,
        start_time=time.time(),
        attributes={
            "run_id": run_id,
            "tenant_id": tenant_id,
            **attributes,
        },
    )
    status = "ok"
    try:
        yield span
    except Exception:
        status = "error"
        raise
    finally:
        span.finish(status=status)
