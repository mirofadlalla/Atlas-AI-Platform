"""
RAG-specific metrics collection module.

This module defines custom Prometheus metrics for RAG pipeline monitoring.
These metrics complement the system metrics in monitors.py and provide
RAG-specific visibility into pipeline performance and efficiency.

Metrics are automatically collected and pushed to Prometheus for visualization
in Grafana dashboards.
"""

from prometheus_client import Counter, Histogram


class RAGMetrics:
    """
    Container for RAG-specific Prometheus metrics.

    These metrics track:
    - Token consumption and costs
    - RAG pipeline latency at different stages
    - Cache hit rates and efficiency
    - Query success/failure rates
    """

    # Token usage tracking for cost analysis
    TOKEN_USAGE_COUNTER = Counter(
        "rag_token_usage_total",
        "Total tokens consumed by LLM",
        ["model_name", "token_type", "tenant_id"],
    )

    # RAG pipeline latency by step
    RAG_LATENCY_HISTOGRAM = Histogram(
        "rag_process_latency_seconds",
        "Latency of RAG steps",
        ["step", "tenant_id"],  # Steps: retrieval, reranking, generation, etc.
    )

    # Semantic cache efficiency
    CACHE_HIT_COUNTER = Counter(
        "rag_cache_hits_total",
        "Number of semantic cache hits",
        ["status", "tenant_id"],  # Status: hit, miss
    )

    # RAG query tracking
    REQUEST_COUNT = Counter(
        "rag_requests_total",
        "Total number of RAG queries",
        ["tenant_id", "status"],  # Status: success, error
    )
