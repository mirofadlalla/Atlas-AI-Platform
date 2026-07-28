from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.routes import auth_route, ingest_rag_route, eval_pipline, query_route, agent_route, internal_metrics_route

from logging_setup import setup_logging

setup_logging() # Initialize logging For docker logs and Sentry

import sentry_sdk
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware

import os

# Initialize Sentry for error tracking
sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    traces_sample_rate=1.0
)

# from app.design_pattern.embedded_model import EmbeddedModel

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     # load model once
#     app.state.embedding_model = EmbeddedModel()
#     print("Models Loaded Successfully ...")
#     yield
#     print("Models Closed Successfully ...")

# import mlflow

app = FastAPI(
    title="Atlas AI Platform",
    description="A platform for RAG and LLM applications",
    version="1.0.0",
    # lifespan=lifespan
)

# Add CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_route.router, prefix="/api", tags=["Authentication"])
app.include_router(ingest_rag_route.router, prefix="/api", tags=["ingest-rag"])
app.include_router(eval_pipline.router, prefix="/api", tags=["eval-rag"])
app.include_router(query_route.router, prefix="/api", tags=["query"])
app.include_router(agent_route.router, prefix="/api", tags=["agent"])
app.include_router(internal_metrics_route.router, prefix="/api", tags=["internal-metrics"])

app.add_middleware(SentryAsgiMiddleware)

# ==================== HEALTH CHECK ENDPOINT ====================

@app.get("/health", tags=["monitoring"])
async def health_check():
    """Health check endpoint for container orchestration and monitoring."""
    return {
        "status": "healthy",
        "service": "Atlas AI Platform",
        "version": "1.0.0"
    }

# ==================== PROMETHEUS & MONITORING ====================
"""
Prometheus metrics integration for monitoring HTTP requests, system resources,
RAG pipeline performance, and agent execution metrics.

The metrics are exposed on the /metrics endpoint for Prometheus scraping.
All metrics are automatically recorded and pushed to the metrics collection.
"""

from prometheus_client import Counter, Histogram, REGISTRY
from prometheus_fastapi_instrumentator import Instrumentator
from app.core.monitors import record_resource_metrics
from starlette.middleware.base import BaseHTTPMiddleware
from time import time
import logging

logger = logging.getLogger(__name__)

# ==================== CUSTOM METRICS MIDDLEWARE ====================

class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Custom middleware for tracking HTTP request and response metrics.
    
    Records:
    - Total HTTP requests by method, endpoint, and status code
    - Request latency (duration from request to response) 
    - HTTP response payload size
    
    These metrics are exposed to Prometheus for alerting and visualization.
    """

    async def dispatch(self, request, call_next):
        """
        Process HTTP request and record metrics.
        
        Args:
            request: FastAPI request object
            call_next: Next middleware/handler
            
        Returns:
            Response with metrics recorded
        """
        start_time = time()
        endpoint = request.url.path

        try:
            response = await call_next(request)
            duration = time() - start_time

            # Import metrics objects
            from app.core.monitors import (
                http_requests_total,
                http_request_duration_seconds,
                http_response_size_bytes,
            )

            method = request.method
            status = response.status_code

            # Record metrics for this request
            http_requests_total.labels(
                method=method, endpoint=endpoint, status_code=status
            ).inc()
            http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(
                duration
            )

            if hasattr(response, "body"):
                http_response_size_bytes.labels(method=method, endpoint=endpoint).observe(
                    len(response.body)
                )

            return response

        except Exception as e:
            logger.error(f"Error in metrics middleware: {e}")
            raise


# ==================== METRICS INITIALIZATION ====================

# Add metrics middleware to track HTTP requests
app.add_middleware(MetricsMiddleware)

# Register Prometheus FastAPI Instrumentator for advanced metrics
# This adds automatic instrumentation for all FastAPI endpoints
Instrumentator().instrument(app).expose(app, endpoint="/metrics", tags=["monitoring"])

# Background task for recording system resource metrics
@app.on_event("startup")
async def startup_event():
    """
    Initialize monitoring tasks on application startup.
    
    Starts background task to periodically record:
    - System CPU usage
    - System memory usage
    - System disk usage
    - Process-specific metrics (memory, file descriptors)
    - Network I/O statistics
    
    These metrics help monitor application health and resource utilization.
    """
    import asyncio

    async def record_metrics_periodically():
        """
        Record system metrics every 10 seconds.
        
        This runs continuously in the background and updates gauge metrics
        for current system and process resource utilization.
        """
        while True:
            try:
                # Call the function that updates all system metrics
                record_resource_metrics()
                await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"Error recording metrics: {e}")
                await asyncio.sleep(10)

    # Start the metrics recording task in background
    asyncio.create_task(record_metrics_periodically())
    logger.info("Prometheus monitoring initialized successfully")