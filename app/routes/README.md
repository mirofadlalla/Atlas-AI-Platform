# Atlas AI — Routes Module (FastAPI API Layer)

## Overview

This module (`app/routes/`) defines Atlas AI's HTTP API surface via FastAPI `APIRouter` instances: authentication/tenant/invitation management, RAG document ingestion, RAG query/answer (streaming), agent-based reasoning (streaming and batch), evaluation pipeline control, recommended Q&A management, memory privacy controls, and an internal-only metrics-recording endpoint used by Celery workers. Routes are thin HTTP adapters — most business logic is delegated to service/controller classes imported from elsewhere in the codebase (not included in this zip), while cross-cutting concerns (rate limiting, MLflow tracking, Prometheus metrics, background task dispatch) are frequently inlined directly in the route handlers themselves, especially in `query_route.py`, `agent_route.py`, `ingest_rag_route.py`, and `eval_pipline.py`.

**Provided code:** `__init__.py` (25 lines), `auth_route.py` (258 lines), `ingest_rag_route.py` (250 lines), `eval_pipline.py` (204 lines), `query_route.py` (535 lines), `agent_route.py` (397 lines), `memory_route.py` (27 lines), `recommended_qa_route.py` (93 lines), `internal_metrics_route.py` (164 lines), plus a pre-existing `README.md`.

**Not provided / Referenced but not provided:** every service/controller class these routes call into (`AuthController`, `TenantRegistrationService`, `UserProfileService`, `InvitationManagementService`, `UserApprovalService`, `RecommendedQAService`, `MLflowService`, `RetrievalPipeline`, `agent_app`/LangGraph agent graph, `CustomLocalLLM`), the auth dependency implementations (`get_current_user`, `require_admin`, `get_db`), the rate limiter (`app.core.rate_limitizer`), the Prometheus metric objects (`app.core.monitors`), the Celery task functions themselves (`ingest_file_task`, `evaluate_task`, `generate_eval_dataset_task`, `trigger_query_logging`, `trigger_semantic_memory_extraction`, `trigger_episode_write`, `trigger_agent_logging`), and the ORM models (`Runs`, `CostLog`). As with prior modules, the pre-existing `README.md` in this folder is not treated as verified ground truth — only the `.py` source files are.

---

## Responsibilities

* Expose HTTP endpoints for: tenant/user registration and login, invitation-based onboarding, admin approval workflows, document upload/ingestion, non-agentic RAG query/answer (streaming), agent-based reasoning (streaming and batch), evaluation pipeline triggering/status, recommended Q&A CRUD, memory-clearing (privacy), and an internal metrics-ingestion endpoint for Celery workers.
* Enforce authentication (`get_current_user`, `require_admin` dependencies) and, in several endpoints, explicit role checks beyond the dependency itself (`recommended_qa_route.py`).
* Enforce per-endpoint rate limiting (`ip_rate_limit`, `rate_limit`) where called.
* Validate uploaded file type/size and sanitize filenames before writing to disk (`ingest_rag_route.py`).
* Derive `tenant_id` exclusively from the authenticated user/admin object (JWT-derived, per multiple inline comments), never from client-supplied request fields, in every route that has one.
* Start/stop MLflow tracking runs around ingestion, evaluation, and query endpoints.
* Enqueue Celery background tasks (`ingest_file_task`, `evaluate_task`, `generate_eval_dataset_task`) and trigger further background logging tasks (`trigger_query_logging`, `trigger_semantic_memory_extraction`, `trigger_episode_write`, `trigger_agent_logging`).
* Record Prometheus metrics both directly (in-process, for the FastAPI app itself) and via a dedicated internal endpoint (`internal_metrics_route.py`) that lets Celery worker processes (which don't share Prometheus registry state with the API process) push metrics back into the API process's registry over HTTP.

## Boundaries

* Routes do not implement retrieval, embedding, agent reasoning, or LLM calling themselves — they call into `RetrievalPipeline`, `agent_app`, and `CustomLocalLLM`, none of which are provided.
* Routes do not implement the actual persistence for auth/invitations/tenants/recommended Q&A — those are delegated to service classes not provided.
* `internal_metrics_route.py` explicitly exists to work around Prometheus's per-process registry model — it does not compute or interpret metrics, only forwards pre-computed values from the payload into the FastAPI process's metric objects.

---

## Project Structure

```
routes/
├── __init__.py                  # Lazy module map: auth_route, ingest_rag_route,
│                                 # eval_pipline, query_route, agent_route,
│                                 # recommended_qa_route, memory_route
├── README.md                     # Pre-existing docs (not verified against source)
├── auth_route.py                 # /auth — tenant registration, login, invitations, approvals
├── ingest_rag_route.py           # /ingest-rag — file upload + ingestion task queueing
├── eval_pipline.py               # /eval — evaluation task queueing + status
├── query_route.py                # /query — RAG ask (streaming), retrieve, cost analytics, runs
├── agent_route.py                # /agent — agent reasoning (streaming + batch)
├── memory_route.py               # /memory — clear all memory for the authenticated user
├── recommended_qa_route.py       # /recommended-qa — per-tenant recommended Q&A CRUD
└── internal_metrics_route.py     # /internal/metrics — Celery-worker-to-API metrics bridge
```

Note: `internal_metrics_route.py` is **not** included in `__init__.py`'s `_ROUTE_MAP`, unlike every other route file — `Not enough information from the provided code` about whether it is mounted elsewhere (e.g. directly in the main FastAPI app) or omitted from lazy-loading deliberately (e.g. always-imported at startup) or simply not wired up. This is a factual gap between the two provided files, not an assumption.

### `__init__.py` — Lazy Route Loading

Uses module-level `__getattr__` (PEP 562) to lazily `importlib.import_module()` each route submodule only when first accessed as an attribute of `app.routes`, rather than importing all seven eagerly. `__all__` lists the same seven keys. This defers each route module's import-time side effects (e.g. `APIRouter()` instantiation, decorator registration) until something actually accesses `app.routes.<name>`.

---

## Request Lifecycle (General Pattern)

Not every route follows every step, but the common shape observed across `query_route.py`, `agent_route.py`, `ingest_rag_route.py`, and `eval_pipline.py` is:

```text
HTTP Request
    │
    ▼
FastAPI dependency injection
    ├─ Depends(get_current_user) / Depends(require_admin)  → current_user / current_admin
    └─ Depends(get_db)                                       → db: Session
    │
    ▼
tenant_id = str(current_user.tenant_id)   ← always derived from the authenticated
                                             principal, never a request field
    │
    ▼
rate_limit(user_id, role, endpoint) / ip_rate_limit(client_ip, endpoint)
    │
    ▼
[optional] MLflow run started (MLflowService.start_run), params logged
    │
    ▼
Route-specific work:
    ├─ ingest_rag_route: validate + sanitize + save file → ingest_file_task.delay(...)
    ├─ eval_pipline: save file → evaluate_task.delay(...) / generate_eval_dataset_task.delay(...)
    ├─ query_route /ask: short-term memory load → cache check → (on miss) semantic +
    │      episodic recall → RetrievalPipeline.retrieve() → streamed generation via
    │      pipeline.ask_stream() → memory writes → trigger_* background logging
    └─ agent_route /ask-agent(-batch): create_initial_state() → agent_app.astream_events()
           / agent_app.ainvoke() → trigger_agent_logging → optional run_id result caching
    │
    ▼
[optional] Prometheus metrics recorded directly; MLflow run ended
    │
    ▼
HTTP Response (JSON or text/event-stream SSE)
```

---

## File-by-File Explanation

### `auth_route.py` — `/auth`

| Endpoint | Method | Auth | Notes |
|---|---|---|---|
| `/auth/tenant/register` | POST | None | Delegates entirely to `TenantRegistrationService(db).register_tenant(request)`; imported lazily inside the function body |
| `/auth/register` | POST | None | Rate-limited via `ip_rate_limit(client_ip=request.client.host, endpoint="register")` — docstring states 5 req/min, but this specific number is not enforced in this file; it lives inside the unprovided `ip_rate_limit` implementation. Delegates to `AuthController.register(user, db)`. |
| `/auth/login` | POST | None | Rate-limited via `ip_rate_limit(..., endpoint="login")` — docstring states 10 req/min, same caveat as above. Delegates to `AuthController.login(user, db)`. |
| `/auth/profile` | GET | `get_current_user` | Delegates to `UserProfileService().get_profile(current_user)`, imported lazily |
| `/auth/invitations/send` | POST | `require_admin` | `tenant_id=str(current_admin.tenant_id)` — inline comment: "Always from JWT — never trust client." Delegates to `InvitationManagementService(db).send_invitation(...)` |
| `/auth/invitations/validate` | GET | None | Query param `token: str`; delegates to `InvitationManagementService(db).validate_invitation(token)` |
| `/auth/register-via-invitation` | POST | None | Delegates to `InvitationManagementService(db).register_via_invitation(token, name, password, tenant_id)` — passes through `request.tenant_id` from the (previously reviewed) `RegisterViaInvitationRequest` schema as-is, unlike `/invitations/send`, which explicitly overrides it from the JWT. This is a genuine, code-level asymmetry: one invitation-adjacent endpoint hard-overrides client-supplied `tenant_id`, the other passes it straight through to the service layer, whose internal handling of that field is not provided. |
| `/auth/invitations/pending` | GET | `require_admin` | Delegates to `InvitationManagementService(db).get_pending_invitations(current_admin.id)` |
| `/auth/invitations/resend` | POST | `require_admin` | Delegates to `InvitationManagementService(db).resend_invitation(request.token)` |
| `/auth/pending-approvals` | GET | `require_admin` | Delegates to `UserApprovalService(db).get_pending_approvals()`; route itself builds the response dict (`total`, `pending_users` list with `user_id`, `name`, `email`, `created_at`) from the returned ORM objects — this is the one place in `auth_route.py` where response shaping happens in the route rather than being returned as-is from a service |
| `/auth/approve-user/{user_id}` | POST | `require_admin` | Delegates to `UserApprovalService(db).approve_user(user_id, current_admin.id)` |
| `/auth/reject-user/{user_id}` | POST | `require_admin` | Delegates to `UserApprovalService(db).reject_user(user_id, current_admin.id)` |

No try/except appears anywhere in `auth_route.py` — every endpoint either succeeds or lets an exception from the delegated service propagate as FastAPI's default 500 response (or whatever exception type the service itself raises, e.g. an `HTTPException` from inside `AuthController`, which is not visible here).

### `ingest_rag_route.py` — `/ingest-rag`

**`POST /ingest-rag/upload_file`** — the only endpoint in this file.

**Security controls present in this file specifically:**
* `ALLOWED_EXTENSIONS`: a fixed set of 12 extensions (`.pdf`, `.txt`, `.md`, `.csv`, `.docx`, `.doc`, `.pptx`, `.ppt`, `.xlsx`, `.xls`, `.html`, `.json`).
* `MAX_FILE_SIZE_BYTES = 50 MB`, enforced **while streaming to disk in 1 MB chunks** (`UPLOAD_CHUNK_SIZE`), not after the full file is buffered in memory — the code explicitly reads and writes in a loop, checking cumulative `total_bytes` after every chunk, and deletes the partially-written file (`file_path.unlink(missing_ok=True)`) before raising `HTTPException(413, ...)` if the limit is exceeded.
* `_safe_filename()`: strips directory components via `Path(original).name` (guards path traversal), then replaces `/`, `\`, and null bytes with `_`. The function's own docstring includes worked examples (`"../etc/passwd" → "etc_passwd"`).
* A UUID prefix (`f"{uuid.uuid4().hex}_{safe_name}"`) is added to the stored filename specifically so two admins uploading identically-named files never collide on disk.
* `tenant_id` is taken from `current_admin.tenant_id` — inline comment: "Fix 2: derive tenant_id from JWT, never from the client" — the phrase "Fix" (also appearing as "Fix 3a", "Fix 3b", "Fix 3c", "Fix 4" at each of the security controls above) implies these were specific remediations added after some prior review, though the nature of the original issue being fixed is not stated in the code itself.

**Flow after validation:** ends any stale MLflow run → starts a new MLflow run (`MLflowService.start_run`, experiment `DEFAULT_EXPERIMENT_INGEST`) → logs params/metrics if the run started → calls `ingest_file_task.delay(file_path=..., tenant_id=..., source=..., author=...)` (the Celery task from the previously-reviewed `celery` module's routing table) → returns `{"message", "task_id", "file", "size_bytes", "status": "processing"}`.

Note: the endpoint accepts `recursive: bool = Form(False)` and `file_extensions: str = Form(None)` as form parameters (matching the `UploadRequest` schema's fields from the previously-reviewed `schema` module), but **neither is passed into `ingest_file_task.delay(...)`** — only `file_path`, `tenant_id`, `source`, `author` are forwarded. This is a concrete, verifiable gap: the endpoint accepts these two parameters but does not use them anywhere in the visible code. Since this endpoint only accepts a single `UploadFile` (not a folder), `recursive`/`file_extensions` would only be meaningful if `ingest_file_task` itself handles multi-file logic — which is not provided.

**Error handling:** a specific exception hierarchy is used — `HTTPException` re-raised unchanged; `PermissionError` → 403; `ValueError` → 400 (message passed through); any other `Exception` → 500 with a generic client-facing message (raw exception details logged server-side only, per the inline "Fix 4" comment: "never leak raw exception details to the client"). A `finally` block always calls `MLflowService.end_run(status="FINISHED")`, itself wrapped in its own try/except so a failure ending the MLflow run doesn't mask the original response/exception.

### `eval_pipline.py` — `/eval`

| Endpoint | Method | Auth | Notes |
|---|---|---|---|
| `/eval/evaluate` | POST | `require_admin` | Rate-limited. Ends stale MLflow run, starts a new one (`DEFAULT_EXPERIMENT_EVAL`), logs params if started, saves the uploaded file to `app/files/eval_files/{original filename}` (no UUID prefixing or filename sanitization here, unlike `ingest_rag_route.py` — a concrete, code-level difference between the two upload endpoints), logs the file as an MLflow artifact, then calls `evaluate_task.delay(tenant_id, path, runs, run_id=mlflow_run_id)`. |
| `/eval/generate_dataset` | POST | `require_admin` | Rate-limited. Calls `generate_eval_dataset_task.delay(tenant_id, max_chunks)` directly — no MLflow run is started for this endpoint, unlike `/evaluate`, another concrete asymmetry within the same file. |
| `/eval/status/{task_id}` | GET | None | No auth dependency present on this endpoint, unlike every other endpoint in this file — a concrete, verifiable observation (whether this is intentional given task IDs are opaque UUIDs, or an oversight, cannot be determined from this file alone). Looks up `celery_app.AsyncResult(task_id)` and returns `{"task_id", "status", "result"}` (result only included if `status == "SUCCESS"`). |

**File save path for `/evaluate`:** `temp_file_path = upload_dir / file.filename` — the raw client-supplied filename is used directly as part of the disk path, with **no path-traversal sanitization** (contrast with `ingest_rag_route.py`'s `_safe_filename()`), and **no file size limit enforcement** (contrast with `ingest_rag_route.py`'s chunked 50 MB cap) — the entire file is read into memory in one call (`await file.read()`) before being written. This is a concrete, code-level difference in security posture between the two upload-handling routes in this module.

**Error handling:** `/evaluate` and `/generate_dataset` both catch a blanket `Exception` and return a generic 500; `/status/{task_id}` does the same. None distinguish specific exception types the way `ingest_rag_route.py`'s upload endpoint does.

### `query_route.py` — `/query`

The largest and most intricate file in this module.

**`POST /query/ask`** (streaming, SSE via `StreamingResponse`) — the central RAG endpoint:

1. `tenant_id` from JWT; rate-limited by `(user_id, role, endpoint)`.
2. Ends stale MLflow run, starts a new one (`DEFAULT_EXPERIMENT_QUERY`), logs params if started.
3. Loads short-term conversation history via `ShortTermMemory().load(tenant_id, user_id, request.session_id)` and flattens it into a `Role: content` string (`short_term_history`).
4. Builds a **cache key deliberately before any semantic/episodic recall or retrieval** — the inline comment explains this ordering choice: short-term history is the only memory layer that "materially changes conversational answers and is part of the key," implying semantic/episodic context is not part of the cache key by design (this is stated directly in the code's comment, not inferred).
5. On a cache hit (`get_local_query_cache(cache_key)`): increments a Prometheus counter (`cache_hits_total.labels(cache_type="local_memory")`), reuses the cached `answer` and `documents`, and skips constructing a `RetrievalPipeline` entirely.
6. On a cache miss: recalls semantic memories (`SemanticMemory().recall(...)`) and recent episode summaries (`EpisodicMemory().get_recent(..., exclude_session_id=request.session_id)`), concatenates them with the short-term history into a combined `chat_history` string, constructs a `RetrievalPipeline(tenant_id=tenant_id, db=db)`, and retrieves documents once via `pipeline.retrieve(request.query)` — the inline comment notes this single retrieval is reused for both the LLM call and the client-facing `documents` SSE event, explicitly stating `/retrieve` is "no longer needed by the query page after an answer request" (implying `/retrieve` exists as a separate, now largely redundant endpoint for a different UI flow).
7. Returns a `StreamingResponse` wrapping an async generator (`answer_generator`) that:
   * On a cache hit: yields the cached answer as a single SSE `answer` event (memory writes/extraction are explicitly **not** re-run on a cache hit — inline comment: "Re-running memory writes/extraction would duplicate long-term data").
   * On a cache miss: streams `pipeline.ask_stream(...)` chunk-by-chunk as SSE `answer` events, accumulating `full_answer`; after streaming completes, saves both the user's question and the assistant's answer to short-term memory (`memory.save(...)` twice, once per role), and triggers two background tasks: `trigger_semantic_memory_extraction(...)` and `trigger_episode_write(...)` (the latter passed the full turn history plus the new user/assistant turns).
   * Always yields a `documents` SSE event (serialized retrieved documents) and a `done` SSE event.
   * Computes cost only on a cache miss, explicitly to avoid reusing stale token-usage state left on the `CustomLocalLLM` singleton by an earlier request (inline comment makes this reasoning explicit): reads `CustomLocalLLM.last_usage`, computes `cost_usd = input_tokens * 0.0000001 + output_tokens * 0.0000002` (a **hardcoded per-token pricing formula present directly in this route**, not sourced from a config or pricing service).
   * Logs MLflow metrics (`latency_seconds`, `cost_usd`, `input_tokens`, `output_tokens`, `answer_length`, `cache_hit`), each wrapped in its own inner try/except so an MLflow failure doesn't affect the response.
   * Records Prometheus metrics directly (`query_pipeline_duration_seconds`, and — only on a cache miss — `llm_queries_total`, `llm_tokens_consumed`, `llm_tokens_generated`, `api_calls_cost_total`, all labeled with a **hardcoded model name string `"Qwen2.5-1.5B"`**).
   * Triggers `trigger_query_logging(...)` (background DB/analytics logging), wrapped in its own try/except.
   * A top-level try/except around the entire generator body yields an `error` SSE event and logs on failure; a `finally` block ends the MLflow run.
8. An outer try/except around the whole route (outside the generator) catches any exception during the *setup* phase (before streaming starts — e.g. memory load, cache lookup, retrieval), marks the MLflow run `FAILED`, and raises a generic 500 `HTTPException`.

**`POST /query/retrieve`** — standalone document retrieval without generation: rate-limited, constructs a fresh `RetrievalPipeline(tenant_id=tenant_id)` (note: **no `db` passed here**, unlike the `/ask` endpoint's `RetrievalPipeline(tenant_id=tenant_id, db=db)` — a concrete, verifiable constructor-argument difference between the two call sites in this same file), calls `pipeline.retrieve(...)`, serializes results via the same `serialize_retrieved_documents` helper used by `/ask`'s `documents` event (inline comment states this is deliberate, to keep the two payloads identical), and returns `{"query", "documents_count", "documents"}`.

**`GET /query/cost-analytics`** — queries `CostLog` joined to `Runs`, filtered by `tenant_id`, grouped by `model_name`, summing cost/input/output tokens per model via SQLAlchemy `func.sum` — this is the one endpoint in the file that builds a raw SQLAlchemy query directly in the route rather than delegating to a service.

**`GET /query/runs`** — queries the last 50 `Runs` rows for the tenant, ordered by `created_at` descending, truncating `query` to 100 chars and `answer` to 200 chars for display — also a direct SQLAlchemy query in the route.

Both `/cost-analytics` and `/runs` import their ORM models (`CostLog`, `Runs`) and SQLAlchemy helpers (`func`, `desc`) lazily, inside the function body, rather than at module level — consistent with the lazy-import pattern used for service classes throughout this module.

### `agent_route.py` — `/agent`

Defines its own `AgentRequest` Pydantic model locally (not imported from the `schema` module reviewed previously): `question` (1–2000 chars, stripped), `run_id: str | None` (documented inline as "optional idempotency key for retries"), `session_id: str | None` (1–128 chars).

**`POST /agent/ask-agent`** (streaming SSE):
1. Builds `inputs` via `create_initial_state(request.question, current_user.tenant_id, run_id=request.run_id, user_id=current_user.id, session_id=request.session_id)`.
2. **Idempotency/caching:** if `request.run_id` is supplied, checks `get_cached_run_result(request.run_id)` *before* invoking the agent at all — if a cached result exists, replays it as SSE events (`answer`, `complete`, `done`) and returns immediately, without touching `agent_app`.
3. Otherwise, iterates `agent_app.astream_events(inputs, version="v2")` (LangGraph's event-streaming API), translating specific event types/names into SSE events:
   * `on_chain_start` for `thought`/`sql_tool`/`retrieval_tool` node names → `tool_start` SSE events with a human-readable tool label.
   * `on_chain_end` — checks `output.get("degraded")`/`degraded_reason` on *every* chain-end event (not just specific nodes) to track a running `degraded`/`degraded_reason` state across the whole execution; then, specifically for the `think` node with a `"thought"` key → `thought` SSE event; for the `finish` node with a `"final_answer"` key → `answer` + `complete` SSE events, and captures `final_result`/`step_count` for post-execution logging; for `sql_tool`/`retrieval_tool`/`think` generically → `tool_end` SSE events.
4. After the stream ends: yields a `done` SSE event, computes latency, reads `CustomLocalLLM.last_usage` for token counts (same pattern as `query_route.py`), and — only if `final_result` was captured (i.e. the `finish` node actually ran) — records Prometheus metrics directly (`agent_queries_total`, `agent_reasoning_steps_total`, `agent_reasoning_duration_seconds`, `agent_reasoning_steps_count`, `llm_tokens_consumed`, `llm_tokens_generated`, `api_calls_cost_total`, again labeled with the hardcoded `"Qwen2.5-1.5B"` model name) and triggers `trigger_agent_logging(...)`.
5. If `request.run_id` was supplied, caches the full result dict via `cache_run_result(request.run_id, cache_response)` for future idempotent replays (step 2 above).
6. A blanket try/except around the SSE loop yields an `error` event and logs on any failure — no `finally`/MLflow cleanup block appears in this endpoint, unlike `query_route.py`'s `/ask` (a concrete, verifiable absence — no MLflow run is started or ended anywhere in `agent_route.py`, in contrast to every other task-queueing/generation endpoint in this module).

**`POST /agent/ask-agent-batch`** (non-streaming): same `create_initial_state` + `run_id` cache-check pattern, but calls `agent_app.ainvoke(inputs)` and awaits the full result rather than streaming events. Reads metrics (`step_count`, `input_tokens`, `output_tokens`, `llm_cost_usd`) directly from the returned state dict (`result.get(...)`) rather than from `CustomLocalLLM.last_usage` (a concrete, code-level difference in how the two agent endpoints source their token/cost figures — the streaming endpoint reads a global singleton's last-call state; the batch endpoint reads fields the agent graph itself returned in its final state). Triggers `trigger_agent_logging(...)` and increments `agent_executions_total` with a `status="success"` label directly in the try block; on any exception, the except block returns `{"success": False, "error": str(e)}` as a **normal 200-status JSON response**, not an `HTTPException` — a concrete, verifiable difference from most other routes in this module, which raise `HTTPException` (typically 500) on unexpected errors instead of returning a 200 with an error payload.

Note: `/ask-agent-batch` also logs with `model_name="llama-3.3-70b-versatile"` (matching the Groq model from the previously-reviewed `design_pattern` module's `LLMService`), while `/ask-agent` (streaming) and both `query_route.py` endpoints use `"Qwen2.5-1.5B"` — a real, verifiable inconsistency in which model name string is attached to logged/metric data across these three generation-triggering endpoints, suggesting either two different LLMs are actually in play depending on code path, or one of the hardcoded labels is stale. This document cannot determine which, since neither `agent_app` nor `CustomLocalLLM` is provided.

### `memory_route.py` — `/memory`

**`DELETE /memory/clear`** — the only endpoint. Authenticated via `get_current_user`. Calls `ShortTermMemory().clear_all(tenant_id, user_id)`, `SemanticMemory().clear_user(user_id, tenant_id)`, and `EpisodicMemory().clear_user(user_id, tenant_id)` — all three memory layers reviewed in the previously-reviewed `memory` module — and returns a combined result dict. No try/except in this route itself; failures inside any of the three memory classes are already fail-open per that module's design (they return `0`/`False` rather than raising), so this route cannot distinguish a partial failure from a legitimate zero-count clear based on the response shape alone.

### `recommended_qa_route.py` — `/recommended-qa`

| Endpoint | Method | Auth | Notes |
|---|---|---|---|
| `` (empty path, i.e. `/recommended-qa`) | GET | `get_current_user` | Delegates to `RecommendedQAService.get_recommended_questions(tenant_id, db)`; docstring states "Max 10 per tenant" but this limit is not enforced in this file — it's presumably enforced inside the unprovided service |
| `` | POST | `get_current_user` + explicit role check | Explicitly checks `getattr(current_user, "role", None) != "admin"` and raises 403 if not — this is a **manual role check inline in the route**, distinct from the `require_admin` FastAPI dependency used in `auth_route.py`/`ingest_rag_route.py`/`eval_pipline.py`. This is the only file in the module that enforces admin-only access this way rather than via a dependency. |
| `/{qa_id}` | DELETE | `get_current_user` + explicit role check | Same manual role check pattern as POST above |

The POST endpoint catches `ValueError` from the service specifically → 400 with the exception message; any other `Exception` → 500 generic message. The DELETE endpoint checks the boolean return of `RecommendedQAService.delete_recommended_question(...)` and raises 404 if falsy — no try/except wraps this call, so an unexpected exception from the service would propagate as an unhandled 500 rather than the generic-message pattern used elsewhere.

### `internal_metrics_route.py` — `/internal/metrics`

**Not authenticated via the normal `get_current_user`/`require_admin` dependencies** — instead uses a separate API-key mechanism: `APIKeyHeader(name="X-Internal-Token", auto_error=False)` combined with a `_verify_internal_token` dependency that compares the header value against `settings.internal_metrics_api_key`, raising 403 if missing/mismatched. The module-level comment explains the purpose: "Celery workers must include this header," and the endpoint's own docstring explains *why* this bridge exists at all — "Prometheus only scrapes the FastAPI process," so Celery tasks (running in separate worker processes with their own, unscraped Prometheus registries) push their metric values here via HTTP so they land in the metric objects living in the FastAPI process's memory, where Prometheus can actually see them.

**`POST /internal/metrics/record`** — accepts an arbitrary JSON body (`Dict[str, Any]`, not a typed Pydantic model, unlike virtually every other POST endpoint in this module), branches on a `metric_type` field (`"query_run"`, `"agent_run"`, `"ingest_run"`, `"eval_run"`) and updates the corresponding Prometheus metric objects (imported from `app.core.monitors`) using values pulled out of the untyped payload via `.get(...)` with defaults. An unrecognized `metric_type` logs a warning and returns `{"status": "error", ...}` as a normal 200 response (not an `HTTPException`) — same "200 with error payload" pattern seen in `agent_route.py`'s batch endpoint. A blanket `except (ValueError, TypeError): pass` inside the per-metric-name loop for `eval_run` scores silently ignores individual malformed score values without logging them, the only place in this entire module where an exception is caught and fully silenced without any log line.

---

## Data Flow — Key Request/Response Shapes

Only shapes actually constructed in this module's route bodies (not the full schema module, which was reviewed separately):

```text
AgentRequest (defined locally in agent_route.py, NOT app.schema)
   question: str (1-2000 chars)
   run_id: str | None
   session_id: str | None
        │
        ▼
create_initial_state(...) → inputs (agent graph state, structure not provided)
        │
        ▼
agent_app.astream_events(...) / agent_app.ainvoke(...)  [LangGraph — not provided]
        │
        ▼
SSE events {type, ...} (streaming) OR a JSON response dict (batch)
```

```text
QueryRequest (app.schema.query_request, previously reviewed)
   query: str (1-2000 chars)
   session_id: str | None
        │
        ▼
ShortTermMemory.load() → short_term_history
        │
        ▼
build_query_cache_key(tenant_id, query, short_term_history, user_id, session_id)
        │
   ┌────┴────┐
   │ hit      │ miss
   ▼          ▼
cached      SemanticMemory.recall() + EpisodicMemory.get_recent()
result        → chat_history; RetrievalPipeline.retrieve() → documents
   │          │
   └────┬─────┘
        ▼
SSE events: answer (chunked), documents, done  [or error]
```

---

## External Dependencies

| Dependency | Purpose | Where Used | Required? |
|---|---|---|---|
| `fastapi` (`APIRouter`, `Depends`, `HTTPException`, `UploadFile`, `File`, `Form`, `Request`, `Security`, `Body`) | HTTP routing, dependency injection, request parsing | All route files | Yes |
| `fastapi.responses.StreamingResponse` | SSE streaming | `query_route.py`, `agent_route.py` | Yes, in those files |
| `fastapi.security.api_key.APIKeyHeader` | Internal service-to-service auth | `internal_metrics_route.py` | Yes, in that file |
| `pydantic` (`BaseModel`, `Field`) | Locally-defined `AgentRequest`, `RecommendedQACreate` | `agent_route.py`, `recommended_qa_route.py` | Yes |
| `sqlalchemy.orm.Session` | DB session type, direct queries | Nearly all route files; direct query usage in `query_route.py` (`/cost-analytics`, `/runs`) | Yes |
| `app.core.db.get_db` | DB session dependency | Nearly all route files | Referenced but not provided |
| `app.core.rate_limitizer` (`ip_rate_limit`, `rate_limit`) | Per-IP and per-user/role rate limiting | `auth_route.py`, `ingest_rag_route.py`, `eval_pipline.py`, `query_route.py` | Referenced but not provided |
| `app.services.auth_services.auth_service` (`get_current_user`, `require_admin`) | Auth dependencies | All routes except `internal_metrics_route.py` (which uses its own key check) | Referenced but not provided |
| `app.services.mlflow_service.MLflowService` | Start/end MLflow runs, param/metric logging helpers | `ingest_rag_route.py`, `eval_pipline.py`, `query_route.py` | Referenced but not provided |
| `app.core.monitors` (Prometheus metric objects) | Direct in-process metric recording | `query_route.py`, `agent_route.py`, `internal_metrics_route.py` | Referenced but not provided |
| `app.rag.retrivel_data_pipline` (`RetrievalPipeline`, `build_query_cache_key`, `get_local_query_cache`, `serialize_retrieved_documents`) | RAG retrieval, caching, generation, serialization | `query_route.py` | Referenced but not provided |
| `app.agent.core.graph.agent_app` | LangGraph agent application | `agent_route.py` | Referenced but not provided |
| `app.agent.observability.metrics.agent_executions_total` | Prometheus counter | `agent_route.py` | Referenced but not provided |
| `app.agent.utils.run_cache` (`cache_run_result`, `get_cached_run_result`) | Idempotent agent-run result caching keyed by `run_id` | `agent_route.py` | Referenced but not provided |
| `app.agent.utils.state_helpers.create_initial_state` | Builds agent graph input state | `agent_route.py` | Referenced but not provided |
| `app.services.llm_runner.CustomLocalLLM` | Source of `last_usage` (token counts) for cost calc | `query_route.py`, `agent_route.py` (streaming only) | Referenced but not provided |
| `app.memory.*` (`ShortTermMemory`, `SemanticMemory`, `EpisodicMemory`, `ConversationTurn`) | Memory read/write | `query_route.py`, `memory_route.py` | Provided in a separately-reviewed module |
| `app.services.semantic_memory_service.trigger_semantic_memory_extraction`, `app.services.episodic_memory_service.trigger_episode_write`, `app.services.rag_services.query_logging_service.trigger_query_logging`, `app.services.rag_services.agent_logging_service.trigger_agent_logging` | Background logging/extraction task triggers (presumed Celery, per the separately-reviewed `celery` module's task routes) | `query_route.py`, `agent_route.py` | Referenced but not provided |
| `app.services.rag_services.ingest_rag_service.ingest_file_task`, `app.services.rag_services.eval_pipline.evaluate_task` / `generate_eval_dataset_task` | Celery task entrypoints | `ingest_rag_route.py`, `eval_pipline.py` | Referenced but not provided (task routing confirmed in the separately-reviewed `celery` module) |
| `app.celery.celery_config.celery_app` | `AsyncResult` lookup for task status | `eval_pipline.py`'s `/status/{task_id}` | Provided in a separately-reviewed module |
| `app.controllers.auth_controller.AuthController` | Register/login logic | `auth_route.py` | Referenced but not provided |
| `app.services.tenant_registration_service.TenantRegistrationService`, `app.services.user_profile_service.UserProfileService`, `app.services.invitation_management_service.InvitationManagementService`, `app.services.user_approval_service.UserApprovalService`, `app.services.recommended_qa_service.RecommendedQAService` | Business logic for their respective domains | `auth_route.py`, `recommended_qa_route.py` | Referenced but not provided |
| `app.models.costLog.CostLog`, `app.models.runs.Runs` | ORM models queried directly | `query_route.py` (`/cost-analytics`, `/runs`) | Referenced but not provided |
| `mlflow` (third-party) | Experiment tracking | `ingest_rag_route.py`, `eval_pipline.py`, `query_route.py` | Yes, where imported |
| `app.core.config.settings` | `internal_metrics_api_key` | `internal_metrics_route.py` | Referenced but not provided |

---

## Configuration

```env
# Referenced via app.core.config.settings — exact env var name not confirmed by this file
INTERNAL_METRICS_API_KEY=<shared-secret-for-celery-to-api-metrics-bridge>   # settings.internal_metrics_api_key
```

No other environment variables are referenced directly in this module — all other configuration (DB URL, rate limit thresholds, MLflow experiment names beyond the `MLflowService.DEFAULT_EXPERIMENT_*` constants referenced, etc.) lives in files not provided.

---

## API Reference (Consolidated)

| Route file | Prefix | Endpoint | Method | Auth |
|---|---|---|---|---|
| `auth_route.py` | `/auth` | `/tenant/register` | POST | None |
| | | `/register` | POST | None (IP rate-limited) |
| | | `/login` | POST | None (IP rate-limited) |
| | | `/profile` | GET | `get_current_user` |
| | | `/invitations/send` | POST | `require_admin` |
| | | `/invitations/validate` | GET | None |
| | | `/register-via-invitation` | POST | None |
| | | `/invitations/pending` | GET | `require_admin` |
| | | `/invitations/resend` | POST | `require_admin` |
| | | `/pending-approvals` | GET | `require_admin` |
| | | `/approve-user/{user_id}` | POST | `require_admin` |
| | | `/reject-user/{user_id}` | POST | `require_admin` |
| `ingest_rag_route.py` | `/ingest-rag` | `/upload_file` | POST | `require_admin` |
| `eval_pipline.py` | `/eval` | `/evaluate` | POST | `require_admin` |
| | | `/generate_dataset` | POST | `require_admin` |
| | | `/status/{task_id}` | GET | **None** (no auth dependency present) |
| `query_route.py` | `/query` | `/ask` | POST | `get_current_user` |
| | | `/retrieve` | POST | `get_current_user` |
| | | `/cost-analytics` | GET | `get_current_user` |
| | | `/runs` | GET | `get_current_user` |
| `agent_route.py` | `/agent` | `/ask-agent` | POST | `get_current_user` |
| | | `/ask-agent-batch` | POST | `get_current_user` |
| `memory_route.py` | `/memory` | `/clear` | DELETE | `get_current_user` |
| `recommended_qa_route.py` | `/recommended-qa` | `` (root) | GET | `get_current_user` |
| | | `` (root) | POST | `get_current_user` + manual admin check |
| | | `/{qa_id}` | DELETE | `get_current_user` + manual admin check |
| `internal_metrics_route.py` | `/internal/metrics` | `/record` | POST | `X-Internal-Token` header, not JWT |

`Not enough information from the provided code` about the top-level path prefix these routers are mounted under (e.g. whether an app-wide `/api` prefix is added when these routers are `include_router()`-ed into the main FastAPI app) — that wiring is not part of this zip.

---

## Async / Background Processing

This module is a heavy producer of asynchronous work, though none of the consuming task code is included:

* `ingest_rag_route.py` and `eval_pipline.py` both call `.delay(...)` on Celery task objects (`ingest_file_task`, `evaluate_task`, `generate_eval_dataset_task`) imported from `app.services.rag_services.*` — matching the task names routed in the previously-reviewed `celery` module's `task_routes`.
* `query_route.py` and `agent_route.py` call `trigger_*` functions (`trigger_query_logging`, `trigger_semantic_memory_extraction`, `trigger_episode_write`, `trigger_agent_logging`) whose own implementations aren't provided — whether these are themselves `.delay()`-wrapped Celery tasks, direct synchronous calls, or something else is `Not enough information from the provided code`, though their naming and the presence of a matching Celery routing table in the separately-reviewed module makes a Celery-task implementation plausible, not confirmed.
* `internal_metrics_route.py` exists specifically because Celery workers run in separate OS processes from the FastAPI app and therefore cannot share in-process Prometheus metric state — this is the concrete, stated reason (in the route's own docstring) for this endpoint's existence, not an inference.
* `eval_pipline.py`'s `/status/{task_id}` endpoint is the only place in this module that reads Celery task state back (`celery_app.AsyncResult(task_id)`), returning `PENDING`/`SUCCESS`/etc. status strings as reported by the Celery result backend.

---

## Observability

* **MLflow:** started/ended around `ingest_rag_route.py`'s upload, `eval_pipline.py`'s `/evaluate` (but not `/generate_dataset`), and `query_route.py`'s `/ask` (but not `/retrieve`, `/cost-analytics`, `/runs`). Notably absent from all of `agent_route.py` — neither `/ask-agent` nor `/ask-agent-batch` starts or ends an MLflow run anywhere in the provided code, a concrete asymmetry with the otherwise-similar `query_route.py` `/ask` endpoint.
* **Prometheus:** metrics are recorded two ways in this module — (1) directly, in-process, inside `query_route.py` and `agent_route.py`'s streaming endpoint, using metric objects imported from `app.core.monitors`; and (2) indirectly, via `internal_metrics_route.py`, which lets out-of-process Celery workers push equivalent metric updates over HTTP using the same underlying metric objects.
* **Logging:** every route file uses the standard `logging` module; error-path logging consistently uses `exc_info=True` for unexpected exceptions across `ingest_rag_route.py`, `eval_pipline.py`, `query_route.py`, and `agent_route.py`'s streaming generator, giving full tracebacks in server logs while HTTP responses carry only a generic message — consistent with the "never leak raw exception details" pattern stated explicitly in `ingest_rag_route.py`.
* **Hardcoded model-name labels used for metrics/logging** across the module: `"Qwen2.5-1.5B"` (query_route.py both metric paths, agent_route.py streaming), `"llama-3.3-70b-versatile"` (agent_route.py batch) — see the note under `agent_route.py` above regarding this inconsistency.

---

## Security

* **Tenant ID derivation:** every authenticated route that has a `tenant_id` concept derives it from `current_user.tenant_id`/`current_admin.tenant_id` (the JWT-derived principal object), never from a request body/query field — this is stated explicitly in inline comments at multiple points (`ingest_rag_route.py`: "Fix 2: derive tenant_id from JWT, never from the client"; `auth_route.py`'s `/invitations/send`: "Always from JWT — never trust client").
* **One exception to that pattern:** `auth_route.py`'s `/register-via-invitation` passes `request.tenant_id` (a client-suppliable, optional field on `RegisterViaInvitationRequest`) straight to `InvitationManagementService.register_via_invitation(...)` without overriding it — unlike `/invitations/send`'s explicit override. Whether the service internally re-derives/validates this value against the invitation record (as its schema's docstring, reviewed previously, implies it should) cannot be confirmed from this file.
* **File upload hardening** (`ingest_rag_route.py`): extension allowlist, 50 MB size cap enforced during chunked streaming (not after full buffering), filename sanitization against path traversal, UUID-prefixed storage names, generic error messages to the client with full details only in server logs. **`eval_pipline.py`'s `/evaluate` upload endpoint does not share any of these controls** — it writes the raw client filename directly into the target path with no sanitization and no size limit, a concrete, code-level gap relative to the ingestion upload endpoint in the same module.
* **Role enforcement is inconsistent in mechanism** across the module: most admin-only endpoints use the `require_admin` FastAPI dependency (`auth_route.py`, `ingest_rag_route.py`, `eval_pipline.py`), while `recommended_qa_route.py` instead performs a manual `getattr(current_user, "role", None) != "admin"` check inline in two of its three endpoints. Both approaches are present in the codebase; this document does not assume one is more or less correct, only notes the inconsistency as a verifiable fact.
* **`internal_metrics_route.py`'s auth is a single shared-secret header comparison** (`api_key != expected`), not JWT-based, and not constant-time (`!=` on strings) — whether this matters depends on threat model details not provided.
* **`eval_pipline.py`'s `/status/{task_id}` endpoint has no auth dependency at all** — any caller who can guess or observe a task ID (a UUID, likely hard to guess, but not confirmed as cryptographically random in this file) can query its status and result. This is a concrete, verifiable gap relative to every other status/data-returning endpoint in the module.
* **`recommended_qa_route.py`'s GET endpoint has no explicit admin check** (any authenticated user, any role, in the tenant can read recommended Q&A) — consistent with it being non-admin-sensitive data, but noted here since the POST/DELETE endpoints on the same resource do enforce admin-only.

---

## Performance

### Implemented Optimizations
* `query_route.py`'s `/ask` deliberately builds the cache key from only the required inputs (query + short-term history) *before* performing semantic recall, episodic recall, or document retrieval — avoiding all three expensive operations entirely on a cache hit.
* The same endpoint retrieves documents exactly once per cache-miss request and reuses that single retrieval for both the LLM prompt and the client-facing `documents` SSE event, rather than retrieving twice.
* `ingest_rag_route.py`'s chunked file write (1 MB chunks) avoids loading an entire large upload into memory before the size check can reject it.
* Route modules are lazily imported via `__init__.py`'s `__getattr__`, avoiding eager import-time cost for routers not actually accessed.

### Potential Optimization Opportunities
* `eval_pipline.py`'s `/evaluate` reads the entire uploaded file into memory in one `await file.read()` call, unlike the chunked approach used in `ingest_rag_route.py` — a potential memory-usage concern for large evaluation datasets, though no size limit is enforced there at all currently, so this is a latent risk rather than a currently-observed failure.
* `query_route.py` and `agent_route.py` both perform lazy, per-request `from app.services.llm_runner import CustomLocalLLM` and other lazy imports inside hot-path functions — Python caches modules after first import, so repeated cost is minimal, but it is a repeated pattern worth noting for readability/maintainability rather than raw performance.

---

## Failure Scenarios

| Failure | Expected Behavior | Impact |
|---|---|---|
| Upload exceeds 50 MB (`ingest_rag_route.py`) | Partially-written file deleted, `HTTPException(413)` raised | Client gets a clear size-limit error; no orphaned file left on disk |
| Upload has disallowed extension (`ingest_rag_route.py`) | `HTTPException(400)` raised before any file write | No file written at all |
| Unexpected error during ingestion (`ingest_rag_route.py`) | Caught by blanket `except Exception`, logged with full traceback, generic 500 returned; MLflow run still ended in `finally` | Client never sees internal exception details |
| Celery broker unreachable when queueing (`ingest_rag_route.py`) | `.delay()` failure caught specifically, logged with type/message, then **re-raised** — propagates to the outer generic-500 handler | Client receives a 500; task was never queued |
| Query/agent generation fails mid-stream (`query_route.py`, `agent_route.py`) | Caught inside the async generator, an `error` SSE event is yielded to the already-open stream | Client sees a partial stream ending in an `error` event rather than an HTTP-level error status, since the response has already started streaming |
| Agent batch execution fails (`agent_route.py` `/ask-agent-batch`) | Caught, returns `{"success": False, "error": str(e)}` as a normal 200 response | Client must inspect the `success` field rather than the HTTP status code to detect failure — differs from most other routes in this module |
| Internal metrics payload has unknown `metric_type` | Logged as a warning, returns `{"status": "error", ...}` as a 200 | Silent from an HTTP-status perspective; caller must check the body |
| Malformed individual score value in `eval_run` metrics payload | Caught by `except (ValueError, TypeError): pass`, silently skipped | That one score is dropped with no log line — the only fully-silent exception handling in this module |
| `/eval/status/{task_id}` called with an invalid/unknown task ID | `Not enough information from the provided code` — depends on what `celery_app.AsyncResult(task_id).status` returns for an unknown ID (typically `"PENDING"` in Celery's own semantics, but that is Celery's behavior, not this route's) | Not determinable from this file alone |

---

## Testing

No tests were provided in the analyzed code.

---

## Deployment

No Dockerfiles, ASGI server startup commands, or environment manifests are included in this zip. `Not enough information from the provided code` about how these routers are mounted into a top-level FastAPI app (path prefixes, CORS, middleware) — none of that wiring is present in this module.

---

## Known Limitations

### Confirmed Limitations
* `internal_metrics_route.py` is excluded from `__init__.py`'s `_ROUTE_MAP`, unlike every other route file in this zip — its actual mounting mechanism is unconfirmed.
* `ingest_rag_route.py`'s `/upload_file` accepts `recursive` and `file_extensions` form fields but does not forward either into the `ingest_file_task.delay(...)` call.
* `eval_pipline.py`'s `/evaluate` upload path has none of the security hardening (filename sanitization, size limit, chunked write) present in `ingest_rag_route.py`'s upload path.
* `eval_pipline.py`'s `/status/{task_id}` has no authentication dependency, unlike every other data-returning endpoint in this module.
* Hardcoded LLM model-name labels used for metrics/logging are inconsistent across `query_route.py` (`"Qwen2.5-1.5B"`), `agent_route.py`'s streaming endpoint (`"Qwen2.5-1.5B"`), and `agent_route.py`'s batch endpoint (`"llama-3.3-70b-versatile"`).
* `agent_route.py` has no MLflow run tracking anywhere, unlike the otherwise-comparable `query_route.py` `/ask` and `ingest_rag_route.py`/`eval_pipline.py`'s primary endpoints.
* `recommended_qa_route.py` enforces admin-only access via a manual inline role check rather than the `require_admin` dependency used consistently elsewhere.
* `auth_route.py`'s `/register-via-invitation` passes a client-suppliable `tenant_id` through to the service layer unmodified, unlike `/invitations/send`'s explicit JWT override of the same conceptual field.
* `query_route.py`'s `/ask` and `/retrieve` construct `RetrievalPipeline` with different constructor arguments (`db=db` passed in one, omitted in the other).

### Potential Risks / Improvements
* Consider applying the same upload-hardening pattern (`_safe_filename`, chunked size-limited writes) used in `ingest_rag_route.py` to `eval_pipline.py`'s `/evaluate` endpoint.
* Consider adding authentication to `/eval/status/{task_id}`, or confirming task IDs are non-guessable and scoped such that this is an accepted design choice.
* Consider centralizing the LLM model-name string used in metrics/logging (e.g. reading it from the actual LLM client/config) rather than hardcoding it separately in three call sites with two different values.
* Consider standardizing on either dependency-based (`require_admin`) or inline role checks for admin-only endpoints, rather than mixing both patterns within the module.

---

## Summary

This module implements Atlas AI's FastAPI route layer across eight route files (plus a lazy-loading `__init__.py`): tenant/user auth and invitation management, hardened file-upload ingestion, evaluation-pipeline triggering and status, a streaming RAG query endpoint with a deliberately-scoped local cache key and single-retrieval reuse, streaming and batch agent-reasoning endpoints with idempotent run-id-based result caching, a memory-privacy clear-all endpoint, admin-managed recommended Q&A, and an internal API-key-protected metrics bridge that lets out-of-process Celery workers push Prometheus data back into the API process. Business logic is consistently delegated to unprovided service/controller classes, while cross-cutting infrastructure concerns (MLflow, Prometheus, rate limiting, Celery task dispatch) are frequently implemented inline within the route handlers themselves — a pattern that is fairly consistent for `ingest_rag_route.py` and `query_route.py`/`agent_route.py`'s core endpoints, but noticeably inconsistent in several specific, verifiable ways documented above (upload hardening present in one upload endpoint but not the other; MLflow tracking present in most generation/ingestion endpoints but entirely absent from `agent_route.py`; three different hardcoded model-name labels used across otherwise-similar metric/logging calls; and two different mechanisms — dependency vs. inline check — used to enforce admin-only access at different points in the module).