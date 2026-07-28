"""
Comprehensive monitoring and metrics collection module for Atlas AI Platform.

This module provides:
- Custom Prometheus metrics for RAG, Agents, and application performance
- Resource utilization tracking
- Business metrics collection
- Middleware integration for automatic request tracking

Monitoring
Metrics Collection
Performance Tracking
Cost Tracking
System Health
Business Analytics

يعني بدل ما تقول:
"السيستم بطيء"

أنت هنا تقدر تعرف بدقة:

أي endpoint بطيء؟
أي tenant يستهلك أكثر؟
كم تكلفة الـ LLM؟
كم وقت الـ retrieval؟
كم chunk تم استرجاعه؟
هل الـ cache فعالة؟
هل الـ agents تفكر كثيرًا؟
هل الـ Celery queue مختنقة؟
هل الـ CPU وصل 95%؟

"""

from prometheus_client import Counter, Histogram, Gauge, Summary
from typing import Optional
import time
import psutil
import logging

logger = logging.getLogger(__name__)

# ==================== REQUEST & RESPONSE METRICS ====================

# HTTP Request metrics
http_requests_total = Counter(
    "atlas_http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code"],
)

http_request_duration_seconds = Histogram(
    "atlas_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

http_request_size_bytes = Histogram(
    "atlas_http_request_size_bytes",
    "HTTP request payload size in bytes",
    ["method", "endpoint"],
    buckets=(100, 1000, 10000, 100000, 1000000),
)

http_response_size_bytes = Histogram(
    "atlas_http_response_size_bytes",
    "HTTP response payload size in bytes",
    ["method", "endpoint"],
    buckets=(100, 1000, 10000, 100000, 1000000),
)

# ==================== RAG PIPELINE METRICS ====================

# Document Ingestion Metrics
documents_ingested_total = Counter(
    "atlas_documents_ingested_total",
    "Total number of documents ingested",
    ["tenant_id", "document_type"],
)

document_ingestion_duration_seconds = Histogram(
    "atlas_document_ingestion_duration_seconds",
    "Time taken to ingest a document (seconds)",
    ["document_type"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

document_chunks_created = Histogram(
    "atlas_document_chunks_created",
    "Number of chunks created per document",
    ["document_type"],
    buckets=(1, 5, 10, 25, 50, 100, 250, 500),
)

duplicate_documents_detected = Counter(
    "atlas_duplicate_documents_detected",
    "Total number of duplicate documents detected",
    ["tenant_id"],
)

# Embedding Metrics
embeddings_generated_total = Counter(
    "atlas_embeddings_generated_total",
    "Total number of embeddings generated",
    ["tenant_id"],
)

embedding_generation_duration_seconds = Histogram(
    "atlas_embedding_generation_duration_seconds",
    "Time to generate embeddings (seconds)",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

embedding_batch_size = Histogram(
    "atlas_embedding_batch_size",
    "Number of texts embedded in a batch",
    buckets=(1, 5, 10, 25, 50, 100, 256, 512),
)

# Retrieval Metrics
vector_search_queries_total = Counter(
    "atlas_vector_search_queries_total",
    "Total number of vector similarity searches",
    ["tenant_id"],
)

vector_search_duration_seconds = Histogram(
    "atlas_vector_search_duration_seconds",
    "Time taken for vector similarity search (seconds)",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

retrieved_chunks_count = Histogram(
    "atlas_retrieved_chunks_count",
    "Number of chunks retrieved per query",
    buckets=(1, 5, 10, 25, 50, 100),
)

retrieval_precision_metric = Gauge(
    "atlas_retrieval_precision",
    "Precision of retrieval (0-1)",
    ["tenant_id"],
)

retrieval_recall_metric = Gauge(
    "atlas_retrieval_recall",
    "Recall of retrieval (0-1)",
    ["tenant_id"],
)

# Reranking Metrics
reranking_queries_total = Counter(
    "atlas_reranking_queries_total",
    "Total number of reranking operations",
    ["reranker_type"],  # cross_encoder, bm25, hybrid
)

reranking_duration_seconds = Histogram(
    "atlas_reranking_duration_seconds",
    "Time taken for reranking (seconds)",
    ["reranker_type"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
)

reranking_score_histogram = Histogram(
    "atlas_reranking_scores",
    "Distribution of reranking scores",
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

# ==================== AGENT & REASONING METRICS ====================

agent_queries_total = Counter(
    "atlas_agent_queries_total",
    "Total number of queries processed by agents",
    ["tenant_id", "agent_type"],
)

agent_reasoning_steps_total = Counter(
    "atlas_agent_reasoning_steps_total",
    "Total number of reasoning steps executed",
    ["tenant_id", "agent_type"],
)

agent_decision_duration_seconds = Histogram(
    "atlas_agent_decision_duration_seconds",
    "Time taken for agent to make a decision (seconds)",
    ["agent_type"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
)

agent_tool_calls_total = Counter(
    "atlas_agent_tool_calls_total",
    "Total number of tool calls by agents",
    ["agent_type", "tool_name"],
)

agent_reasoning_steps_count = Histogram(
    "atlas_agent_reasoning_steps_count",
    "Number of steps in agent reasoning",
    buckets=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
)

agent_reasoning_duration_seconds = Histogram(
    "atlas_agent_reasoning_duration_seconds",
    "Time taken for complete agent reasoning (seconds)",
    ["agent_type"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

# ==================== QUERY & GENERATION METRICS ====================

llm_queries_total = Counter(
    "atlas_llm_queries_total",
    "Total number of LLM queries",
    ["tenant_id", "model_name"],
)

llm_query_duration_seconds = Histogram(
    "atlas_llm_query_duration_seconds",
    "Time taken for LLM query (seconds)",
    ["model_name"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0),
)

llm_tokens_generated = Counter(
    "atlas_llm_tokens_generated",
    "Total number of tokens generated by LLM",
    ["tenant_id", "model_name"],
)

llm_tokens_consumed = Counter(
    "atlas_llm_tokens_consumed",
    "Total number of tokens consumed (input + output)",
    ["tenant_id", "model_name"],
)

llm_response_quality_score = Gauge(
    "atlas_llm_response_quality",
    "Quality score of LLM response (0-1)",
    ["tenant_id"],
)

# Query latency (end-to-end)
query_pipeline_duration_seconds = Histogram(
    "atlas_query_pipeline_duration_seconds",
    "Complete query pipeline latency (seconds)",
    ["pipeline_stage"],  # retrieval, reranking, generation, total
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)

# ==================== AUTHENTICATION & SECURITY METRICS ====================

authentication_attempts_total = Counter(
    "atlas_authentication_attempts_total",
    "Total authentication attempts",
    ["status"],  # success, failure
)

authentication_duration_seconds = Histogram(
    "atlas_authentication_duration_seconds",
    "Authentication latency (seconds)",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0),
)

active_user_sessions = Gauge(
    "atlas_active_user_sessions",
    "Number of active user sessions",
    ["tenant_id"],
)

invalid_token_attempts = Counter(
    "atlas_invalid_token_attempts",
    "Attempts to use invalid tokens",
    ["tenant_id"],
)

# ==================== COST & BILLING METRICS ====================

api_calls_cost_total = Counter(
    "atlas_api_calls_cost_total",
    "Total cost of API calls in USD",
    ["tenant_id", "service"],  # llm, embedding, retrieval
)

tokens_cost_total = Counter(
    "atlas_tokens_cost_total",
    "Total cost of tokens in USD",
    ["tenant_id", "model_name"],
)

cost_per_query = Histogram(
    "atlas_cost_per_query",
    "Cost per query in USD",
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
)

tenant_monthly_cost = Gauge(
    "atlas_tenant_monthly_cost",
    "Monthly cost per tenant in USD",
    ["tenant_id"],
)

# ==================== DATABASE METRICS ====================

database_connection_pool_size = Gauge(
    "atlas_database_connection_pool_size",
    "Current database connection pool size",
)

database_query_duration_seconds = Histogram(
    "atlas_database_query_duration_seconds",
    "Database query execution time (seconds)",
    ["query_type"],
    buckets=(0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0),
)

database_errors_total = Counter(
    "atlas_database_errors_total",
    "Total database errors",
    ["error_type"],
)

active_database_connections = Gauge(
    "atlas_active_database_connections",
    "Number of active database connections",
)

# ==================== CACHE METRICS ====================

cache_hits_total = Counter(
    "atlas_cache_hits_total",
    "Total cache hits",
    ["cache_type"],  # redis, embedding_cache, etc.
)

cache_misses_total = Counter(
    "atlas_cache_misses_total",
    "Total cache misses",
    ["cache_type"],
)

cache_size_bytes = Gauge(
    "atlas_cache_size_bytes",
    "Cache size in bytes",
    ["cache_type"],
)

# ==================== SYSTEM RESOURCE METRICS ====================

system_cpu_usage_percent = Gauge(
    "atlas_system_cpu_usage_percent",
    "System CPU usage percentage (0-100)",
)

system_memory_usage_percent = Gauge(
    "atlas_system_memory_usage_percent",
    "System memory usage percentage (0-100)",
)

system_disk_usage_percent = Gauge(
    "atlas_system_disk_usage_percent",
    "System disk usage percentage (0-100)",
)

process_cpu_usage_percent = Gauge(
    "atlas_process_cpu_usage_percent",
    "Process CPU usage percentage",
)

process_memory_usage_mb = Gauge(
    "atlas_process_memory_usage_mb",
    "Process memory usage in MB",
)

process_open_file_descriptors = Gauge(
    "atlas_process_open_file_descriptors",
    "Number of open file descriptors",
)

network_io_bytes_sent = Counter(
    "atlas_network_io_bytes_sent",
    "Network bytes sent",
)

network_io_bytes_received = Counter(
    "atlas_network_io_bytes_received",
    "Network bytes received",
)

# ==================== TASK QUEUE METRICS (CELERY) ====================

celery_task_total = Counter(
    "atlas_celery_task_total",
    "Total Celery tasks",
    ["task_name", "status"],  # received, started, succeeded, failed
)

celery_task_duration_seconds = Histogram(
    "atlas_celery_task_duration_seconds",
    "Celery task execution duration (seconds)",
    ["task_name"],
    buckets=(0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0),
)

celery_task_queue_size = Gauge(
    "atlas_celery_task_queue_size",
    "Number of tasks in Celery queue",
    ["queue_name"],
)

celery_active_tasks = Gauge(
    "atlas_celery_active_tasks",
    "Number of active Celery tasks",
)

# ==================== ERROR & EXCEPTION METRICS ====================

application_errors_total = Counter(
    "atlas_application_errors_total",
    "Total application errors",
    ["error_type", "endpoint"],
)

exception_count = Counter(
    "atlas_exceptions_total",
    "Total exceptions raised",
    ["exception_type"],
)

# ==================== EVALUATION METRICS ====================

evaluation_runs_total = Counter(
    "atlas_evaluation_runs_total",
    "Total evaluation runs",
    ["tenant_id"],
)

evaluation_score = Gauge(
    "atlas_evaluation_score",
    "Evaluation score (0-1)",
    ["tenant_id", "metric_name"],
)

evaluation_duration_seconds = Histogram(
    "atlas_evaluation_duration_seconds",
    "Evaluation execution time (seconds)",
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 300.0),
)

# ==================== HELPER FUNCTIONS ====================

def record_resource_metrics():
    """Record current system resource utilization metrics."""
    try:
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        system_cpu_usage_percent.set(cpu_percent)

        # Memory metrics
        memory = psutil.virtual_memory()
        system_memory_usage_percent.set(memory.percent)

        # Disk metrics
        disk = psutil.disk_usage("/")
        system_disk_usage_percent.set(disk.percent)

        # Process-specific metrics
        process = psutil.Process()
        process_cpu_usage_percent.set(process.cpu_percent(interval=0.1))
        process_memory_usage_mb.set(process.memory_info().rss / (1024 * 1024))
        process_open_file_descriptors.set(process.num_fds() if hasattr(process, "num_fds") else 0)

        # Network metrics
        net_io = psutil.net_io_counters()
        network_io_bytes_sent._value.get()  # Get current value
        network_io_bytes_received._value.get()

    except Exception as e:
        logger.error(f"Error recording resource metrics: {e}")


class MetricsContext:
    """Context manager for measuring and recording metrics."""

    def __init__(self, duration_metric, labels: Optional[dict] = None):
        self.duration_metric = duration_metric
        self.labels = labels or {}
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        if self.labels:
            self.duration_metric.labels(**self.labels).observe(duration)
        else:
            self.duration_metric.observe(duration)
        return False


def track_llm_cost(
    tenant_id: str,
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    cost: float,
):
    """Track LLM usage and costs."""
    llm_tokens_consumed.labels(tenant_id=tenant_id, model_name=model_name).inc(
        input_tokens + output_tokens
    )
    llm_tokens_generated.labels(tenant_id=tenant_id, model_name=model_name).inc(
        output_tokens
    )
    api_calls_cost_total.labels(tenant_id=tenant_id, service="llm").inc(cost)
    tokens_cost_total.labels(tenant_id=tenant_id, model_name=model_name).inc(cost)
    cost_per_query.observe(cost)


def track_retrieval_metrics(
    tenant_id: str,
    chunks_retrieved: int,
    duration: float,
    precision: Optional[float] = None,
    recall: Optional[float] = None,
):
    """Track retrieval pipeline metrics."""
    vector_search_queries_total.labels(tenant_id=tenant_id).inc()
    vector_search_duration_seconds.observe(duration)
    retrieved_chunks_count.observe(chunks_retrieved)

    if precision is not None:
        retrieval_precision_metric.labels(tenant_id=tenant_id).set(precision)
    if recall is not None:
        retrieval_recall_metric.labels(tenant_id=tenant_id).set(recall)


def track_agent_execution(
    tenant_id: str,
    agent_type: str,
    steps: int,
    duration: float,
    success: bool,
):
    """Track agent execution metrics."""
    agent_queries_total.labels(tenant_id=tenant_id, agent_type=agent_type).inc()
    agent_reasoning_steps_count.observe(steps)
    agent_reasoning_duration_seconds.labels(agent_type=agent_type).observe(duration)

    if success:
        agent_decision_duration_seconds.labels(agent_type=agent_type).observe(duration)


def track_authentication(success: bool, duration: float):
    """Track authentication metrics."""
    status = "success" if success else "failure"
    authentication_attempts_total.labels(status=status).inc()
    authentication_duration_seconds.observe(duration)
