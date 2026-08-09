# Atlas AI — Celery Background Task Module

## Overview

This module (`app/celery/celery_config.py`) configures the Celery distributed task queue used by Atlas AI for asynchronous / background processing. It is a **configuration module only** — it defines the `Celery` application instance, its broker/backend connections, queue topology, task routing table, serialization, worker pool behavior, time limits, retry policy, and a periodic ("beat") schedule.

**Provided code:** `celery_config.py` (104 lines), plus a pre-existing `README.md` in the same folder.

**Not provided:** the actual task implementations (e.g. `ingest_file_task`, `evaluate_task`, `log_query_run_and_cost`, `extract_semantic_memory`, `write_episode`), the FastAPI routes that presumably enqueue them, the database/vector-store repositories they use, and any Docker/deployment manifests. Everything about *what the tasks actually do* is therefore **Referenced but not provided** — this document does not describe their internal logic, only what can be inferred from how they are registered and routed in `celery_config.py`.

> Note: an existing `README.md` was found alongside the config file containing example task implementations, route handlers, and monitoring code. Since that content is documentation/example code rather than the actual Atlas AI source, it is **not treated as verified implementation** in this document. Only `celery_config.py` is treated as ground truth.

---

## Responsibilities

* Instantiate and configure the shared `celery_app` object used app-wide (`atlas_ai`).
* Define the message broker and result backend connections.
* Declare the queue topology (exchange + queues + routing keys).
* Route specific, named tasks to specific queues.
* Set serialization, worker pool, time-limit, retry, and tracking behavior.
* Autodiscover and explicitly import task modules so workers register them.
* Define a periodic task via Celery Beat.

## Boundaries

* This file does not define any task logic itself — no `@celery_app.task` functions appear in it.
* It does not define the FastAPI application, database models, or vector store — those are only referenced by dotted path in `task_routes` and `conf.imports`.
* It does not configure Prometheus/Flower/monitoring — none of that is present in the provided file.

---

## Project Structure

```
celery/
├── README.md            # Pre-existing docs (not verified against source; see note above)
├── celery_config.py     # Celery app instance, queues, routing, worker/time/retry config, beat schedule
└── __pycache__/         # Compiled bytecode (not source)
```

`Not enough information from the provided code` regarding any other files in `app/celery/` or the broader `app/` tree.

---

## How It Works / Architecture

```text
                 ┌───────────────────────────────┐
                 │   Producer (Not Provided)      │
                 │   e.g. FastAPI route calling    │
                 │   some_task.delay(...)          │
                 └───────────────┬────────────────┘
                                 │  publishes message
                                 ▼
                 ┌───────────────────────────────┐
                 │  Broker: AMQP (RabbitMQ)        │
                 │  CELERY_BROKER_URL env var,     │
                 │  default amqp://guest:guest@    │
                 │  localhost:5672//               │
                 └───────────────┬────────────────┘
                                 │
                   "atlas_ai_exchange" (direct exchange)
                                 │
        ┌────────────────────────┼───────────────────────┬───────────────────┐
        ▼                        ▼                        ▼                   ▼
┌─────────────────┐   ┌────────────────────┐   ┌────────────────────┐  ┌───────────────┐
│ ingest_data_queue│   │  eval_data_queue    │   │  logging_queue      │  │  queue_dead    │
│ routing_key=     │   │  routing_key=       │   │  routing_key=       │  │  routing_key=  │
│ "ingest"         │   │  "eval"              │   │  "logging" (default)│  │  "dead"        │
└────────┬─────────┘   └──────────┬──────────┘   └──────────┬──────────┘  └────────────────┘
         │                        │                          │             (declared, not
         ▼                        ▼                          ▼              routed to by any
┌─────────────────────────────────────────────────────────────────────┐     task in this file)
│                   Celery Worker(s) (Not Provided)                    │
│  consume from queue(s), execute task function, ack late,             │
│  restart after 10 tasks, one task in-flight per prefetch slot        │
└───────────────────────────┬───────────────────────────────────────┘
                            │ result
                            ▼
                 ┌───────────────────────────────┐
                 │ Result Backend: rpc://          │
                 │ (CELERY_RESULT_BACKEND env var) │
                 └───────────────────────────────┘
```

`Not enough information from the provided code` about who consumes the result backend or whether callers poll for results — no producer code is included.

---

## Configuration (`celery_config.py`)

### Celery App Instantiation

```python
celery_app = Celery(
    "atlas_ai",
    broker=os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "rpc://"),
)
```

* App name: `atlas_ai`.
* Broker: AMQP (RabbitMQ), configurable via `CELERY_BROKER_URL`, defaulting to a local guest/guest RabbitMQ instance.
* Result backend: `rpc://` (Celery's RPC/AMQP-based backend), configurable via `CELERY_RESULT_BACKEND`.

### Exchange and Queues

```python
default_exchange = Exchange("atlas_ai_exchange", type="direct")

celery_app.conf.task_queues = (
    Queue("ingest_data_queue", default_exchange, routing_key="ingest"),
    Queue("eval_data_queue", default_exchange, routing_key="eval"),
    Queue("logging_queue", default_exchange, routing_key="logging"),
    Queue("queue_dead", default_exchange, routing_key="dead"),
)
```

A single direct exchange, `atlas_ai_exchange`, routes to four declared queues. `queue_dead` is declared but no task in this file is routed to it, and no dead-lettering mechanism (e.g. `x-dead-letter-exchange` policy) is configured in the provided code — its use is `Not enough information from the provided code`.

### Default Routing

```python
celery_app.conf.task_default_queue = "logging_queue"
celery_app.conf.task_default_exchange = "atlas_ai_exchange"
celery_app.conf.task_default_routing_key = "logging"
```

Any task not explicitly matched in `task_routes` falls back to `logging_queue`.

### Explicit Task Routing Table

| Task (dotted path) | Queue | Routing Key |
|---|---|---|
| `app.services.rag_services.ingest_rag_service.ingest_file_task` | `ingest_data_queue` | `ingest` |
| `app.services.rag_services.eval_pipline.evaluate_task` | `eval_data_queue` | `eval` |
| `app.services.rag_services.eval_pipline.generate_eval_dataset_task` | `eval_data_queue` | `eval` |
| `app.services.rag_services.query_logging_service.log_query_run_and_cost` | `logging_queue` | `logging` |
| `app.services.semantic_memory_service.extract_semantic_memory` | `logging_queue` | `logging` |
| `app.services.semantic_memory_service.prune_low_importance_semantic_memories` | `logging_queue` | `logging` |
| `app.services.episodic_memory_service.write_episode` | `logging_queue` | `logging` |

None of these task functions are present in the provided code — their argument signatures, business logic, and error handling are `Referenced but not provided`.

### Serialization

```python
task_serializer="json"
result_serializer="json"
accept_content=["json"]
```

Only JSON is accepted for both task arguments and results; this restricts task arguments to JSON-serializable types.

### Worker Pool Settings

| Setting | Value | Effect |
|---|---|---|
| `worker_pool` | `"threads"` | Uses a thread pool instead of the default prefork (process) pool — the code comment states this is for better Windows compatibility |
| `worker_max_tasks_per_child` | `10` | Worker thread/child is recycled after 10 tasks (mitigates memory growth) |
| `worker_prefetch_multiplier` | `1` | Each worker process fetches only one task at a time from the queue |
| `worker_disable_rate_limits` | `False` | Per-task rate limits (if set on individual tasks) remain enforced |

### Time Limits

| Setting | Value |
|---|---|
| `task_soft_time_limit` | 550s (9m10s) — a `SoftTimeLimitExceeded` exception is raised inside the task, allowing cleanup |
| `task_time_limit` | 600s (10m) — the worker process/thread is forcibly terminated |

### Retry / Acknowledgement

| Setting | Value | Effect |
|---|---|---|
| `task_acks_late` | `True` | Message is acknowledged only after the task finishes (success or failure), not upon receipt |
| `task_reject_on_worker_lost` | `True` | If the worker dies mid-task, the message is rejected/requeued rather than silently lost |
| `task_default_retry_delay` | 30s | Default wait before a retried task is attempted again |
| `task_max_retries` | 3 | Default cap on retry attempts |

Note: `task_acks_late=True` combined with non-idempotent task logic can cause duplicate execution if a worker crashes after completing side effects but before acknowledging. Whether the referenced tasks are idempotent is `Not enough information from the provided code`.

### Tracking / Timezone

```python
task_track_started=True
timezone="UTC"
enable_utc=True
```

Enables the `STARTED` task state (visible to anything inspecting task state, e.g. via the result backend) and standardizes all task-related timestamps to UTC.

### Task Discovery

```python
celery_app.autodiscover_tasks(["app.services"])
celery_app.conf.imports = (
    "app.services.semantic_memory_service",
    "app.services.episodic_memory_service",
)
```

`autodiscover_tasks` looks for `tasks.py` (or equivalent, depending on Celery's Django/module conventions) inside `app.services`. The code comment explains the explicit `conf.imports` entry exists because the semantic and episodic memory service modules are **not** named `tasks.py`, so autodiscovery would otherwise miss them; they must be imported directly for the worker process to register their `@celery_app.task`-decorated functions.

### Beat Schedule (Periodic Tasks)

```python
celery_app.conf.beat_schedule = {
    "prune-low-importance-semantic-memories-nightly": {
        "task": "app.services.semantic_memory_service.prune_low_importance_semantic_memories",
        "schedule": 24 * 60 * 60,
    }
}
```

One periodic task is configured: `prune_low_importance_semantic_memories`, run every 24 hours (86,400 seconds) via Celery Beat. This requires a separate `celery beat` process to be running in addition to worker processes — beat itself is not started anywhere in the provided code.

---

## External Dependencies

| Dependency | Purpose | Where Used | Required? |
|---|---|---|---|
| Celery | Task queue framework | Entire file | Yes |
| Kombu (`Exchange`, `Queue`) | Message routing primitives underlying Celery | Queue/exchange declarations | Yes |
| RabbitMQ (AMQP broker) | Message broker for task dispatch | `broker=` connection string | Yes (default), overridable via `CELERY_BROKER_URL` |
| RPC/AMQP result backend | Stores/returns task results | `backend="rpc://"` | Yes (default), overridable via `CELERY_RESULT_BACKEND` |
| `app.services.rag_services.*` | Task implementations for ingestion and evaluation | Referenced in `task_routes` | Referenced but not provided |
| `app.services.semantic_memory_service` | Task implementations for semantic memory extraction/pruning | Referenced in `task_routes`, `conf.imports`, `beat_schedule` | Referenced but not provided |
| `app.services.episodic_memory_service` | Task implementation for episodic memory writes | Referenced in `task_routes`, `conf.imports` | Referenced but not provided |

---

## Configuration (Environment Variables)

```env
CELERY_BROKER_URL=<your-amqp-broker-url>          # default: amqp://guest:guest@localhost:5672//
CELERY_RESULT_BACKEND=<your-result-backend-url>   # default: rpc://
```

No other environment variables, settings classes, credentials, model names, or feature flags appear in the provided code.

---

## Async / Background Processing

* **What runs asynchronously:** any task registered under the dotted paths in `task_routes`, plus anything Celery discovers under `app.services` or explicitly imports (`semantic_memory_service`, `episodic_memory_service`). These execute inside separate worker processes/threads, not in the calling request thread.
* **What runs synchronously:** `Not enough information from the provided code` — no producer/caller code (e.g. FastAPI routes calling `.delay()`) is included in this module.
* **Task lifecycle:** message published to `atlas_ai_exchange` with a routing key → routed to the matching queue → picked up by a worker (thread pool, prefetch=1) → executed → acknowledged only after completion (`task_acks_late=True`) → result (if any) sent to the `rpc://` backend.
* **Retry behavior:** default retry delay of 30s and max 3 retries are configured at the app level; whether individual tasks override these or call `self.retry(...)` explicitly is `Not enough information from the provided code` since no task bodies are provided.
* **Periodic task:** `prune_low_importance_semantic_memories` is scheduled every 24 hours via `beat_schedule`, requiring a running `celery beat` process.
* **Why asynchronous processing exists:** the implementation suggests background processing is intended to keep potentially slow operations — document ingestion, evaluation runs, and logging/memory writes — off the synchronous request path, based on the task names and queue naming (`ingest_data_queue`, `eval_data_queue`, `logging_queue`). This inference is drawn from naming conventions only; no producer code confirms it.

---

## Error Handling

Configured at the app level:

* `task_acks_late=True` — a task is only acknowledged (removed from the queue) after it finishes, so a crashed worker leaves the message for redelivery.
* `task_reject_on_worker_lost=True` — if the worker process is lost mid-execution, the unacknowledged message is rejected (and, depending on broker/queue configuration, requeued) instead of being dropped.
* `task_default_retry_delay=30`, `task_max_retries=3` — default backoff/retry ceiling for tasks; actual retry invocation (e.g. `self.retry()`) is task-specific and not present in this file.
* `task_soft_time_limit=550` / `task_time_limit=600` — long-running tasks are first given a soft signal to exit gracefully, then hard-killed 50 seconds later if still running.
* A `queue_dead` queue is declared for potential dead-lettering, but no task routes to it and no RabbitMQ dead-letter-exchange policy is set in the provided code — so it is **not automatically populated** by anything shown here.

`Not enough information from the provided code` regarding: behavior when RabbitMQ is unreachable at startup, exception handling inside individual tasks, or what happens to results if the `rpc://` backend is unavailable.

---

## Observability

`task_track_started=True` is the only observability-related setting present — it makes the `STARTED` state available to anything querying task status via the result backend. No logging, metrics (Prometheus), tracing, or MLflow integration appears in `celery_config.py`. The pre-existing `README.md` in this folder shows example Prometheus counter/histogram code, but this is example/aspirational code, not part of the provided `celery_config.py` source, so it is documented here only as **Referenced but not provided**.

---

## Security

* Broker credentials are read from an environment variable (`CELERY_BROKER_URL`) rather than hardcoded, except for the default fallback `amqp://guest:guest@localhost:5672//`, which uses RabbitMQ's default guest/guest credentials. This default is insecure for anything beyond local development and should be overridden via the environment variable in any shared/production environment.
* No message signing, TLS configuration, authentication of task producers, or per-tenant isolation is present in this file.
* Because `task_serializer` and `accept_content` are both restricted to `"json"`, the config avoids Celery's insecure default pickle deserialization — this is a concrete, present security control.
* `Not implemented / not visible in the provided code`: any tenant isolation for task arguments (e.g. tenant_id validation), authentication between producers and the broker beyond the connection string, or authorization checks on which callers may enqueue which tasks.

---

## Performance

### Implemented Optimizations
* `worker_prefetch_multiplier=1` avoids a single worker hoarding many queued tasks, improving fairness across workers under uneven load.
* `worker_max_tasks_per_child=10` bounds per-process memory growth by recycling workers periodically.
* Dedicated queues per task category (`ingest_data_queue`, `eval_data_queue`, `logging_queue`) allow independent scaling/consumption of different workloads, since consumers can be started against a subset of queues (`--queues=` flag) — though the worker startup commands themselves are not part of this file.

### Potential Optimization Opportunities
* `worker_pool="threads"` limits true parallelism for CPU-bound task code compared to Celery's default prefork pool, though it may suit I/O-bound tasks (e.g. network calls to embedding APIs, databases).
* The `rpc://` result backend does not persist results beyond the RPC exchange lifecycle in the way Redis/database backends do — if task results need to be queried later or by multiple consumers, a persistent backend may be preferable. This is a potential consideration, not a confirmed limitation, since no code shows how results are consumed.

---

## Failure Scenarios

| Failure | Expected Behavior (per provided config) | Impact |
|---|---|---|
| RabbitMQ broker unreachable | `Not enough information from the provided code` — no startup/connection-retry logic shown | Task publishing/consumption would fail; downstream behavior not specified |
| Worker process crashes mid-task | Message is not acked (`task_acks_late=True`) and is rejected/requeued (`task_reject_on_worker_lost=True`) | Task is redelivered to another worker; task should be idempotent to avoid duplicate side effects (idempotency not verifiable from this file) |
| Task exceeds soft time limit (550s) | A `SoftTimeLimitExceeded` exception is raised inside the task | Task can catch this and clean up; behavior depends on task code, not shown |
| Task exceeds hard time limit (600s) | Worker is forcibly terminated | Task is killed; per `task_acks_late`/`task_reject_on_worker_lost`, message handling follows the same requeue path as a lost worker |
| Result backend (`rpc://`) unavailable | `Not enough information from the provided code` | Not specified |

---

## Testing

No tests were provided in the analyzed code.

---

## Deployment

No Dockerfiles, docker-compose manifests, process managers, or startup scripts are included in the provided code. The module implies (via `broker`/`backend` defaults) that a RabbitMQ instance is expected to be reachable, and via `beat_schedule` that a separate `celery beat` process is required alongside worker process(es) to actually run the periodic pruning task. Concrete startup commands, container definitions, health checks, and worker-to-queue assignment in deployment are `Not enough information from the provided code`.

---

## Known Limitations

### Confirmed Limitations
* Default broker credentials (`guest:guest`) are used if `CELERY_BROKER_URL` is not set — insecure outside local development.
* `queue_dead` is declared but nothing in this file routes tasks to it or configures a dead-letter policy, so failed/expired messages are not automatically captured by it based on this configuration alone.
* No observability (metrics/tracing/logging) is configured in this file.

### Potential Risks / Improvements
* Consider a persistent result backend (e.g. Redis) if task results must be queried after the fact by other services.
* Consider wiring `queue_dead` to an actual RabbitMQ dead-letter-exchange policy or explicit task-level error routing if failed-task capture is desired.
* Consider environment-based enforcement (e.g. failing startup) if `CELERY_BROKER_URL` is unset in non-local environments, to avoid silently using default guest credentials.

---

## Summary

`celery_config.py` defines the Celery application (`atlas_ai`) for Atlas AI's background processing layer: an AMQP/RabbitMQ broker with an RPC result backend, four queues on a single direct exchange (`ingest_data_queue`, `eval_data_queue`, `logging_queue`, `queue_dead`), explicit routing for seven named tasks spanning RAG ingestion/evaluation, query cost logging, and semantic/episodic memory maintenance, JSON-only serialization, a thread-based worker pool with periodic recycling, late acknowledgement with requeue-on-worker-loss, bounded retries, and a nightly Beat-scheduled pruning task. The actual task logic, producers (API routes), and deployment topology are referenced by name only and were not included in the provided code, so this document does not describe their behavior beyond what the routing table and comments in `celery_config.py` reveal.
