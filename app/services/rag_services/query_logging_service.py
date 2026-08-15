"""
Background task service for RAG query logging.

Handles asynchronous logging of runs and costs to avoid blocking query responses.
Records both database logs and Prometheus metrics for monitoring and analytics.
"""

import logging
import threading

import requests
from celery import shared_task

from app.repositories.cost_log_repository import CostLogRepository
from app.repositories.runs_repository import RunsRepository
from app.core.db import get_db

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
    try:
        db = next(get_db())

        runs_repo = RunsRepository(db)
        cost_repo = CostLogRepository(db)

        cost_usd = (input_tokens * 0.0000001) + (output_tokens * 0.0000002)

        run = runs_repo.create(
            tenant_id=tenant_id,
            query=query,
            answer=answer,
            latency=latency,
            cache_hit=cache_hit,
            retrieved_docs_ids=retrieved_docs_ids,
        )

        if input_tokens > 0 or output_tokens > 0:
            cost_repo.create(
                run_id=run.run_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model_name=model_name,
                cost_usd=cost_usd,
            )
            logger.info(
                f"Logged run {run.run_id} - Tenant: {tenant_id}, "
                f"Tokens: {input_tokens + output_tokens}, Cost: ${cost_usd:.6f}"
            )
        else:
            logger.info(
                f"Logged run {run.run_id} - Tenant: {tenant_id} (no token usage)"
            )

        try:
            import os
            from app.core.config import settings

            api_host = os.environ.get("API_HOST", "http://localhost:8000")
            if not api_host.startswith("http"):
                api_host = f"http://{api_host}"

            webhook_url = f"{api_host}/api/internal/metrics/record"

            payload = {
                "metric_type": "query_run",
                "tenant_id": str(tenant_id),
                "model_name": model_name,
                "input_tokens": int(input_tokens),
                "output_tokens": int(output_tokens),
                "cost_usd": float(cost_usd),
                "latency": float(latency),
            }

            headers = {}
            if settings.internal_metrics_api_key:
                headers["X-Internal-Token"] = settings.internal_metrics_api_key

            response = requests.post(
                webhook_url, json=payload, headers=headers, timeout=2.0
            )
            if response.status_code == 200:
                logger.debug(
                    f"Successfully sent query metrics to API webhook for run {run.run_id}"
                )
            else:
                logger.warning(
                    f"API webhook returned status {response.status_code}: {response.text}"
                )

        except Exception as metric_error:
            logger.error(
                f"Error recording Prometheus metrics via webhook: {metric_error}"
            )

        db.close()

    except Exception as exc:
        logger.error(f"Error logging query run and cost: {exc}")
        raise self.retry(exc=exc, countdown=min(60 * (2**self.request.retries), 600))


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
    Dispatches task queueing in a daemon thread so broker outages never delay HTTP responses.
    """

    def _enqueue():
        try:
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
                retry=False,
            )
            logger.debug(f"Queued logging task for query: {query[:50]}...")
        except Exception as e:
            logger.warning(f"Failed to queue logging task: {e}")

    threading.Thread(target=_enqueue, daemon=True).start()
