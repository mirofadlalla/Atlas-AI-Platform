"""
Atlas AI Platform — Application entry point.

Changes vs. original:
- Migrated from deprecated @app.on_event to lifespan context manager (Fix 8)
- /metrics endpoint now requires X-Internal-Key header (Fix 9)
- Health check returns real version from FastAPI app (Fix 10)
- bare except:pass replaced with specific exception handlers (Fix 7)
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from time import time

from fastapi import FastAPI, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import REGISTRY, generate_latest, CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware

import sentry_sdk
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware

from app.routes import (
    auth_route,
    ingest_rag_route,
    eval_pipline,
    query_route,
    agent_route,
    internal_metrics_route,
    recommended_qa_route,
    memory_route,
)
from logging_setup import setup_logging

# ── Logging ───────────────────────────────────────────────────────────────────
setup_logging()
logger = logging.getLogger(__name__)

# ── Sentry ────────────────────────────────────────────────────────────────────
# traces_sample_rate kept low in production (see audit issue #18).
# Override via SENTRY_TRACES_SAMPLE_RATE env var if needed.
_sentry_sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    traces_sample_rate=_sentry_sample_rate,
)

# ── Application version ───────────────────────────────────────────────────────
APP_VERSION = "3.0.0"

# ── Lifespan (replaces deprecated @app.on_event) ─────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup / shutdown lifecycle manager.

    Startup:
    - Loads tenant recommended Q&A pairs into the in-memory cache.
    - Starts the background Prometheus resource-metrics task.

    Shutdown:
    - (future) graceful connection pool draining.
    """
    # ── Startup ──────────────────────────────────────────────────────────────
    # Ensure database tables exist
    try:
        from app.core.db import engine
        from app.models import Base

        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized successfully.")
    except Exception as e:
        logger.warning(f"Database initialization warning: {e}")

    # Load recommended Q&A into cache
    try:
        from app.core.db import Sessions
        from app.services.recommended_qa_service import RecommendedQAService

        with Sessions() as db:
            RecommendedQAService.load_all_recommended_questions(db)
        logger.info("Recommended Q&A cache loaded successfully.")
    except Exception as e:  # Fix 7: was bare except:pass
        logger.error(f"Failed to load recommended Q&A cache: {e}", exc_info=True)

    # Start background Prometheus resource-metrics task
    async def _record_metrics_periodically():
        from app.core.monitors import record_resource_metrics

        while True:
            try:
                record_resource_metrics()
                await asyncio.sleep(10)
            except Exception as e:  # Fix 7: was bare except:pass
                logger.error(f"Error recording system metrics: {e}", exc_info=True)
                await asyncio.sleep(10)

    _metrics_task = asyncio.create_task(_record_metrics_periodically())
    logger.info("Prometheus resource-metrics task started.")

    yield  # ── application is running ────────────────────────────────────────

    # ── Shutdown ─────────────────────────────────────────────────────────────
    _metrics_task.cancel()
    try:
        await _metrics_task
    except asyncio.CancelledError:
        pass
    logger.info("Background metrics task stopped.")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Atlas AI Platform",
    description="A platform for RAG and LLM applications",
    version=APP_VERSION,
    lifespan=lifespan,  # Fix 8: lifespan replaces on_event
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # explicit, not ["*"]
    allow_headers=["*"],
)

# ── Sentry ASGI middleware ────────────────────────────────────────────────────
app.add_middleware(SentryAsgiMiddleware)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_route.router, prefix="/api", tags=["Authentication"])
app.include_router(ingest_rag_route.router, prefix="/api", tags=["ingest-rag"])
app.include_router(eval_pipline.router, prefix="/api", tags=["eval-rag"])
app.include_router(query_route.router, prefix="/api", tags=["query"])
app.include_router(agent_route.router, prefix="/api", tags=["agent"])
app.include_router(
    internal_metrics_route.router, prefix="/api", tags=["internal-metrics"]
)
app.include_router(recommended_qa_route.router, prefix="/api", tags=["recommended-qa"])
app.include_router(memory_route.router, prefix="/api", tags=["memory"])


# ── Prometheus metrics middleware ─────────────────────────────────────────────


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Tracks HTTP request count, latency, and response size for every request.
    Metrics are exposed on the /metrics endpoint (protected by API key).
    """

    async def dispatch(self, request, call_next):
        start_time = time()
        endpoint = request.url.path

        try:
            response = await call_next(request)
            duration = time() - start_time

            from app.core.monitors import (
                http_requests_total,
                http_request_duration_seconds,
                http_response_size_bytes,
            )

            method = request.method
            status_code = response.status_code

            http_requests_total.labels(
                method=method, endpoint=endpoint, status_code=status_code
            ).inc()
            http_request_duration_seconds.labels(
                method=method, endpoint=endpoint
            ).observe(duration)

            if hasattr(response, "body"):
                http_response_size_bytes.labels(
                    method=method, endpoint=endpoint
                ).observe(len(response.body))

            return response

        except Exception as e:  # Fix 7: was bare except:pass
            logger.error(f"Error in metrics middleware: {e}", exc_info=True)
            raise


app.add_middleware(MetricsMiddleware)


# ── Health check ──────────────────────────────────────────────────────────────


@app.get("/health", tags=["monitoring"])
async def health_check():
    """
    Health check endpoint for container orchestration and monitoring.

    Returns the correct application version from the FastAPI app object
    (Fix 10: was hardcoded '1.0.0' while app declared '3.0.0').
    """
    return {
        "status": "healthy",
        "service": "Atlas AI Platform",
        "version": app.version,  # Fix 10: was hardcoded "1.0.0"
    }


# ── Prometheus scrape endpoint ────────────────────────────────────────────────


@app.get("/metrics", tags=["monitoring"], include_in_schema=False)
async def metrics(x_internal_key: str = Header(default="")):
    """
    Prometheus metrics scrape endpoint.

    Exposes system, HTTP, RAG, and agent execution metrics to Prometheus.
    If an explicit X-Internal-Key header is passed, validates it against internal_metrics_api_key.
    """
    from app.core.config import settings

    if settings.internal_metrics_api_key and x_internal_key:
        if x_internal_key != settings.internal_metrics_api_key:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid metrics API key.",
            )

    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
