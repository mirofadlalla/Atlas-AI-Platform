"""
Internal metrics route.

Thin HTTP adapter — all business logic lives in InternalMetricsController.
Celery workers post metric payloads here so they land in the FastAPI
process's Prometheus registry and get scraped on /metrics.
"""

import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Body, Security
from fastapi.security.api_key import APIKeyHeader

from app.core.config import settings
from app.controllers.internal_metrics_controller import InternalMetricsController

logger = logging.getLogger(__name__)

# Internal API key security — Celery workers must include this header
_internal_key_header = APIKeyHeader(name="X-Internal-Token", auto_error=False)


def _verify_internal_token(api_key: str = Security(_internal_key_header)):
    """Allow only callers that present the correct internal service token."""
    expected = settings.internal_metrics_api_key
    if not expected or api_key != expected:
        raise HTTPException(
            status_code=403, detail="Invalid or missing internal service token"
        )


router = APIRouter(prefix="/internal/metrics", tags=["internal-metrics"])


@router.post("/record")
async def record_metrics(
    payload: Dict[str, Any] = Body(...),
    _: None = Depends(_verify_internal_token),
):
    """
    Internal endpoint to record Prometheus metrics from background Celery workers.

    Since Prometheus only scrapes the FastAPI process, Celery tasks send their
    metric data here via HTTP so it's registered in the FastAPI app's memory
    and exposed on /metrics.
    """
    return InternalMetricsController.record_metrics(payload)
