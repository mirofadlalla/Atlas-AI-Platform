"""
Background task service for RAG query logging.

Handles asynchronous logging of runs and costs to avoid blocking query responses.
Records both database logs and Prometheus metrics for monitoring and analytics.
"""
import logging
from celery import shared_task
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.repositories.runs_repository import RunsRepository
from app.repositories.cost_log_repository import CostLogRepository
import requests

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def log_query_run_and_cost(
    self,
    tenant_id: str,
    query: str,
    answer: str,
    latency: float,
    cache_hit: bool,
    retrieved_docs_ids: str,
    input_tokens: int,
    output_tokens: float,
    model_name: str = "Qwen2.5-1.5B",
):
    """
    Background task to log query runs and costs to the database.
    
    Also records Prometheus metrics via internal API webhook for monitoring.
    Runs asynchronously to avoid blocking the response stream.
    Retries up to 3 times on failure.
    
    Args:
        tenant_id: Tenant identifier
        query: Original user query
        answer: Generated answer
        latency: Query processing latency in seconds
        cache_hit: Whether response was cached
        retrieved_docs_ids: Comma-separated document IDs used
        input_tokens: Number of input tokens used
        output_tokens: Number of output tokens used
        model_name: LLM model name used
    """
    try:
        # Get a fresh database session for this task
        db = next(get_db())
        
        runs_repo = RunsRepository(db)
        cost_repo = CostLogRepository(db)
        
        # Calculate cost
        cost_usd = (input_tokens * 0.0000001) + (output_tokens * 0.0000002)
        
        # Save run record
        run = runs_repo.create(
            tenant_id=tenant_id,
            query=query,
            answer=answer,
            latency=latency,
            cache_hit=cache_hit,
            retrieved_docs_ids=retrieved_docs_ids
        )
        
        # Save cost log if tokens were used
        if input_tokens > 0 or output_tokens > 0:
            cost_repo.create(
                run_id=run.run_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model_name=model_name,
                cost_usd=cost_usd
            )
            logger.info(
                f"Logged run {run.run_id} - Tenant: {tenant_id}, "
                f"Tokens: {input_tokens + output_tokens}, Cost: ${cost_usd:.6f}"
            )
        else:
            logger.info(f"Logged run {run.run_id} - Tenant: {tenant_id} (no token usage)")
        
        # Record Prometheus metrics via internal webhook so they register on the API server
        try:
            import os
            # For standalone monitoring: Prometheus in Docker reaches host via host.docker.internal
            # For orchestrated: Use service name 'api' in Docker network
            api_host = os.environ.get("API_HOST", "http://host.docker.internal:8000")
            if "localhost" in api_host and not api_host.startswith("http"):
                api_host = f"http://{api_host}"
            
            # Send metrics to FastAPI so Prometheus can scrape them
            webhook_url = f"{api_host}/api/internal/metrics/record"
            
            payload = {
                "metric_type": "query_run",
                "tenant_id": str(tenant_id),
                "model_name": model_name,
                "input_tokens": int(input_tokens),
                "output_tokens": int(output_tokens),
                "cost_usd": float(cost_usd),
                "latency": float(latency)
            }
            
            # Fire and forget with short timeout so Celery task doesn't hang
            response = requests.post(webhook_url, json=payload, timeout=2.0)
            if response.status_code == 200:
                logger.debug(f"Successfully sent query metrics to API webhook for run {run.run_id}")
            else:
                logger.warning(f"API webhook returned status {response.status_code}: {response.text}")
                
        except Exception as metric_error:
            logger.error(f"Error recording Prometheus metrics via webhook: {metric_error}")
            # Don't fail the entire task if metrics recording fails
        
        # Clean up database session
        db.close()
        
    except Exception as exc:
        logger.error(f"Error logging query run and cost: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=min(60 * (2 ** self.request.retries), 600))


def trigger_query_logging(
    tenant_id: str | int,
    query: str,
    answer: str,
    latency: float,
    cache_hit: bool,
    retrieved_docs_ids: str,
    input_tokens: int,
    output_tokens: float,
    model_name: str = "Qwen2.5-1.5B",
) -> None:
    """
    Trigger background logging task without blocking.
    
    This function returns immediately, allowing the response to stream
    while logging happens in the background.
    
    Args:
        tenant_id: Tenant identifier
        query: Original user query
        answer: Generated answer
        latency: Query processing latency in seconds
        cache_hit: Whether response was cached
        retrieved_docs_ids: Comma-separated document IDs used
        input_tokens: Number of input tokens used
        output_tokens: Number of output tokens used
        model_name: LLM model name used
    """
    try:
        # Queue the logging task to run in background
        log_query_run_and_cost.apply_async(
            args=(
                tenant_id,
                query,
                answer,
                latency,
                cache_hit,
                retrieved_docs_ids,
                input_tokens,
                output_tokens,
                model_name,
            ),
            queue="logging_queue",
            routing_key="logging",
        )
        logger.debug(f"Queued logging task for query: {query[:50]}...")
    except Exception as e:
        logger.error(f"Failed to queue logging task: {e}")
        # Log error but don't fail the response
