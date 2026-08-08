from fastapi import APIRouter, Depends, HTTPException, Body, Security
from fastapi.security.api_key import APIKeyHeader
from typing import Dict, Any
import logging

from app.core.config import settings

from app.core.monitors import (
    track_llm_cost,
    query_pipeline_duration_seconds,
    agent_queries_total,
    agent_reasoning_steps_count,
    agent_reasoning_duration_seconds,
    agent_decision_duration_seconds,
    documents_ingested_total,
    document_ingestion_duration_seconds,
    document_chunks_created,
    evaluation_runs_total,
    evaluation_duration_seconds,
    evaluation_score,
)

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
    payload: Dict[str, Any] = Body(...), _: None = Depends(_verify_internal_token)
):
    """
    Internal endpoint to record Prometheus metrics from background Celery workers.

    Since Prometheus only scrapes the FastAPI process, Celery tasks send their
    metric data here via HTTP so it's registered in the FastAPI app's memory
    and exposed on /metrics.
    """
    try:
        metric_type = payload.get("metric_type")
        tenant_id = payload.get("tenant_id", "unknown")

        if metric_type == "query_run":
            # Track Query metrics
            model_name = payload.get("model_name", "unknown")
            input_tokens = payload.get("input_tokens", 0)
            output_tokens = payload.get("output_tokens", 0)
            cost_usd = payload.get("cost_usd", 0.0)
            latency = payload.get("latency", 0.0)

            # Track LLM cost and token usage
            track_llm_cost(
                tenant_id=str(tenant_id),
                model_name=model_name,
                input_tokens=int(input_tokens),
                output_tokens=int(output_tokens),
                cost=float(cost_usd),
            )

            # Record query pipeline latency
            query_pipeline_duration_seconds.labels(pipeline_stage="total").observe(
                float(latency)
            )

            logger.debug(f"Recorded internal query metrics for tenant {tenant_id}")

        elif metric_type == "agent_run":
            # Track Agent execution metrics
            step_count = payload.get("step_count", 0)
            latency = payload.get("latency", 0.0)
            model_name = payload.get("model_name", "unknown")
            input_tokens = payload.get("input_tokens", 0)
            output_tokens = payload.get("output_tokens", 0)
            cost_usd = payload.get("cost_usd", 0.0)

            agent_queries_total.labels(
                tenant_id=str(tenant_id), agent_type="reasoning"
            ).inc()

            agent_reasoning_steps_count.observe(int(step_count))
            agent_reasoning_duration_seconds.labels(agent_type="reasoning").observe(
                float(latency)
            )
            agent_decision_duration_seconds.labels(agent_type="reasoning").observe(
                float(latency)
            )

            track_llm_cost(
                tenant_id=str(tenant_id),
                model_name=model_name,
                input_tokens=int(input_tokens),
                output_tokens=int(output_tokens),
                cost=float(cost_usd),
            )

            logger.debug(f"Recorded internal agent metrics for tenant {tenant_id}")

        elif metric_type == "ingest_run":
            # Track Ingestion metrics
            chunks_created = payload.get("chunks_created", 0)
            latency = payload.get("latency", 0.0)

            document_type = payload.get("document_type", "unknown")
            documents_ingested_total.labels(
                tenant_id=str(tenant_id), document_type=document_type
            ).inc()

            document_ingestion_duration_seconds.labels(
                document_type=document_type
            ).observe(float(latency))
            if chunks_created > 0:
                document_chunks_created.labels(document_type=document_type).observe(
                    int(chunks_created)
                )

            logger.debug(f"Recorded internal ingest metrics for tenant {tenant_id}")

        elif metric_type == "eval_run":
            # Track Evaluation metrics
            latency = payload.get("latency", 0.0)
            scores = payload.get("scores", {})
            runs_count = payload.get("runs", 1)

            evaluation_runs_total.labels(tenant_id=str(tenant_id)).inc(runs_count)
            evaluation_duration_seconds.observe(float(latency))

            # Record individual metric scores if provided
            for metric_name, score_value in scores.items():
                if score_value is not None:
                    try:
                        evaluation_score.labels(
                            tenant_id=str(tenant_id), metric_name=metric_name
                        ).set(float(score_value))
                    except (ValueError, TypeError):
                        pass

            logger.debug(f"Recorded internal evaluation metrics for tenant {tenant_id}")

        else:
            logger.warning(f"Unknown metric type received: {metric_type}")
            return {"status": "error", "message": f"Unknown metric type: {metric_type}"}

        return {"status": "success", "message": "Metrics recorded successfully"}

    except Exception as e:
        logger.error(f"Error recording internal metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while recording metrics. Please try again.",
        )
