# Atlas AI — `services` Module

## Overview

This module (`app/services`) is the **business-logic / orchestration layer** of Atlas AI. It sits between the FastAPI route handlers and the repository/data-access layer, and between Celery workers and the database. It does not define its own HTTP routes, ORM models, or Celery app — it imports those from sibling packages (`app.repositories`, `app.models`, `app.celery.celery_config`, `app.core.*`, `app.rag.*`, `app.memory.*`, `app.design_pattern.*`).

Only the `services` package was provided for analysis (18 Python files, ~2,800 lines). Files such as the Agent Graph, the RAG retriever/reranker, the vector DB client, the memory store implementations, the Celery app config, and the FastAPI routers are **referenced but not provided**, so this README documents only what is proven by the code in this package, and explicitly marks everything else.

### Responsibilities (confirmed by code)
- Authentication, JWT issuance/validation, password hashing (`auth_services/`, `token_service.py`, `hash_service.py`)
- Multi-tenant onboarding: tenant registration, user invitations, admin approval workflow (`tenant_registration_service.py`, `invitation_service.py`, `invitation_management_service.py`, `user_approval_service.py`)
- User profile retrieval (`user_profile_service.py`)
- Transactional email (`email_service.py`)
- LLM invocation wrapper for LangChain (`llm_runner.py`)
- Experiment tracking via MLflow (`mlflow_service.py`)
- Asynchronous (Celery) logging of RAG queries and agent runs, plus a webhook bridge to Prometheus (`rag_services/query_logging_service.py`, `rag_services/agent_logging_service.py`)
- Asynchronous ingestion and evaluation task wrappers (`rag_services/ingest_rag_service.py`, `rag_services/eval_pipline.py`, `rag_services/path_processing_service.py`)
- Asynchronous memory-writing tasks: episodic-memory summarization and semantic-memory extraction (`episodic_memory_service.py`, `semantic_memory_service.py`)
- Per-tenant in-memory cache of "recommended questions" (`recommended_qa_service.py`)

### What this module depends on
- `app.repositories.*` (UserRepository, TenantRepository, InvitationRepository, RunsRepository, CostLogRepository) — data access
- `app.models.*` (Users, RecommendedQA, Base) — ORM models
- `app.core.config.settings`, `app.core.db.get_db` / `get_db_session` — configuration and DB session management
- `app.core.rate_limitizer.rate_limit` — rate limiting
- `app.celery.celery_config.celery_app` and the `celery.shared_task` decorator — background task infrastructure
- `app.design_pattern.llm_singlton.LLMService` — the actual LLM client (not provided)
- `app.design_pattern.upload_factory_pattern.*` — factory pattern for file/folder processors (not provided)
- `app.rag.ingest_data_pipline.RAGPipeline`, `app.rag.evaluation.eval_pipline.EvalPipeline`, `app.rag.evaluation.generate_eval_dataset` — RAG pipeline internals (not provided)
- `app.memory.episodic_memory.EpisodicMemory`, `app.memory.summarizer.SessionSummarizer`, `app.memory.memory_extractor.MemoryExtractor`, `app.memory.semantic_memory.SemanticMemory` — memory backends (not provided)
- External libraries: `sqlalchemy`, `fastapi`, `jose` (python-jose), `passlib` (argon2/bcrypt), `mlflow`, `langchain_core`, `celery`, `requests`, `smtplib`

### What depends on this module
- Not provided directly, but structurally: FastAPI route handlers call these service classes (constructor pattern `Service(db)` then method calls that raise `HTTPException`, which is a FastAPI-specific exception — confirms these services are called from route handlers). Celery workers invoke the `@shared_task`/`@celery_app.task` functions defined here.

---

## Project Structure

```
services/
├── __init__.py
├── README.md                          (pre-existing, partially outdated — see note below)
├── auth_services/
│   ├── auth_admin_service.py          # AuthService: registration + login (issues JWT)
│   └── auth_service.py                # FastAPI dependencies: get_current_user, require_admin
├── email_service.py                   # EmailService: SMTP sending (invitation/welcome/approval emails)
├── episodic_memory_service.py         # Celery task: summarize + store episodic memory
├── hash_service.py                    # password_hash / verify_password (passlib)
├── invitation_management_service.py   # InvitationManagementService: HTTP-facing wrapper w/ rate limiting
├── invitation_service.py              # InvitationService: core invitation lifecycle logic
├── llm_runner.py                      # call_llama() + CustomLocalLLM (LangChain LLM adapter)
├── mlflow_service.py                  # MLflowService: experiment/run logging helpers
├── rag_services/
│   ├── __init__.py                    # re-exports logging trigger functions
│   ├── agent_logging_service.py       # Celery task: log agent run + cost + Prometheus webhook
│   ├── eval_pipline.py                # Celery tasks: evaluate_task, generate_eval_dataset_task
│   ├── ingest_rag_service.py          # Celery task: ingest_file_task
│   ├── path_processing_service.py     # PathProcessingService: factory-pattern file/folder ingestion
│   └── query_logging_service.py       # Celery task: log query run + cost + Prometheus webhook
├── recommended_qa_service.py          # RecommendedQAService: per-tenant in-memory Q&A cache
├── semantic_memory_service.py         # Celery tasks: extract + prune semantic memory
├── tenant_registration_service.py     # TenantRegistrationService: create tenant + first admin
├── token_service.py                   # create_access_token / decode_access_token (JWT)
├── user_approval_service.py           # UserApprovalService: admin approve/reject pending users
└── user_profile_service.py            # UserProfileService: get_profile
```

> **Note on the pre-existing `README.md`**: it states `llm_runner.py` wraps the **OpenAI API** with GPT‑4/GPT‑3.5 support and cost tracking. The actual code in `llm_runner.py` wraps a local `LLMService` singleton (`app.design_pattern.llm_singlton.LLMService`) and a Groq-style Llama model (`llama-3.3-70b-versatile`), with **no OpenAI client and no direct cost computation**. This documentation follows the code, not the old README.

---

## How It Works — File by File

### `auth_services/auth_admin_service.py` — `AuthService`
**Responsibility:** Admin self-registration (which also creates a new tenant) and login, both issuing JWTs.

- `register_user(user_data)`: rejects if the email already exists; rejects if the tenant name already exists (`404` — note this is a questionable status code for a "conflict," but that is what the code does); creates the tenant, hashes the password, creates the user with `role="admin"`, and returns a bearer JWT containing `sub`, `user_id`, `role`, `approval_status`, `tenant_id`.
- `login_user(email, password)`: verifies password via `verify_password`; blocks login with `403` if `approval_status` is `"pending"` or `"rejected"`; otherwise returns a bearer JWT with the same claim set.

**Dependencies:** `UserRepository`, `TenantRepository`, `hash_service`, `token_service`.

### `auth_services/auth_service.py` — FastAPI auth dependencies
**Responsibility:** Provides `get_current_user` and `require_admin` as FastAPI `Depends()` functions, using `OAuth2PasswordBearer(tokenUrl="auth/login")`.

- `get_current_user`: decodes the JWT (`decode_access_token`), extracts `sub` (email), re-fetches the user from the DB by email on **every request**, and re-checks `approval_status == "approved"` on every request — meaning an admin revoking a user's approval takes effect on the user's very next request, without needing to revoke the token itself.
- `require_admin`: wraps `get_current_user` and raises `403` if `role != "admin"`.

### `token_service.py`
**Responsibility:** JWT creation/decoding using `python-jose`, `HS256`.

- Fails hard at **import time** (`raise RuntimeError`) if `settings.api_secret_key` is not configured — there is deliberately no fallback secret.
- `create_access_token(data, expires_delta=None)`: default expiry is 60 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES = 60`).
- `decode_access_token(token)`: raises `JWTError` on invalid/expired tokens (caught by `auth_service.py`).

### `hash_service.py`
**Responsibility:** Password hashing via `passlib.CryptContext`, schemes `["argon2", "bcrypt"]`, default `argon2`, `deprecated="auto"` (so bcrypt hashes still verify but new hashes use argon2).

### `email_service.py` — `EmailService`
**Responsibility:** SMTP-based transactional email with a **dev-mode fallback**: if `settings.smtp_username`/`smtp_password` are unset, `send_email` does not raise — it logs the full email body (including invitation tokens) at `WARNING` level and returns `False`. This is a convenience for local development but is a **potential data-exposure risk** if such logs are shipped to a non-development log aggregator.
- `send_email`: builds a multipart MIME message, connects via `smtplib.SMTP`, calls `starttls()`, logs in, sends, and returns `True`/`False`. All exceptions are caught and logged — callers cannot distinguish failure reasons, only success/failure.
- `send_invitation_email`, `send_welcome_email`, `send_approval_status_email`: template-specific wrappers that build HTML/plain-text bodies and delegate to `send_email`.

### `invitation_service.py` — `InvitationService`
**Responsibility:** Core invitation lifecycle (creation, validation, acceptance, resend, cancel), operating directly on `InvitationRepository` and `UserRepository`.

- Tokens: `secrets.token_hex(32)` → 64 hex characters, cryptographically random. `TOKEN_EXPIRY_DAYS = 7`.
- `send_invitation`: rejects if the invited email already has a user in the same tenant, or if an existing **valid** (non-expired, pending) invitation already exists for that email; otherwise creates the invitation and — best-effort, exceptions are caught and only logged — sends the invitation email.
- `validate_invitation` / `get_invitation_details`: look up by token and check `invitation.is_valid()` (method defined on the `Invitation` model, not provided here).
- `accept_invitation_and_register`: re-validates the token, checks `invitation.tenant_id == tenant_id` (tenant-boundary check on invitation acceptance), checks the user doesn't already exist, then creates the user with `role="user"` and **`approval_status="pending"`** — i.e., invited users still require admin approval before they can log in (this is enforced later by `auth_service.get_current_user` and `AuthService.login_user`).
- `resend_invitation`: expires the old invitation and calls `send_invitation` again to mint + email a new token.

### `invitation_management_service.py` — `InvitationManagementService`
**Responsibility:** HTTP-facing wrapper around `InvitationService` that adds **rate limiting** and consistent `HTTPException` translation/response-shaping (converts datetimes to ISO strings, etc.) for the route layer.

- `send_invitation`: calls `app.core.rate_limitizer.rate_limit(user_id=admin_id, role="admin", endpoint="/auth/invitations/send")` before delegating — the actual rate-limit algorithm/backend is **not provided** in this package.
- `register_via_invitation`: resolves `tenant_id` and `name` from the invitation if not explicitly supplied (falls back to the email's local-part as the name), hashes the password, and calls `InvitationService.accept_invitation_and_register`, then issues a JWT (note: the JWT here does **not** include a `user_id` claim, unlike `AuthService.register_user`/`login_user` — see "Known Limitations").
- `get_pending_invitations`, `resend_invitation`: thin wrappers with logging and error translation.

### `tenant_registration_service.py` — `TenantRegistrationService`
**Responsibility:** Creates a brand-new tenant plus its first admin user in one transaction.

- Rejects duplicate organization names (`409`) and duplicate admin emails (`409`).
- The first admin is created with `approval_status="approved"` directly (no approval workflow for the tenant's first user, unlike invited users).
- Sends a welcome email best-effort (failure is logged, not raised).
- On any exception, calls `self.tenant_repo.rollback()` before re-raising/translating — this is the one service in the package that explicitly demonstrates transactional rollback on failure.

### `user_approval_service.py` — `UserApprovalService`
**Responsibility:** Admin-only workflow to approve/reject users whose `approval_status == "pending"`.

- `authorize_admin(user_role, action)`: raises `403` if the caller's role isn't `"admin"` — note this takes a raw `user_role` string, not a `Depends()`-injected user, so callers are responsible for invoking it explicitly (this is a manual authorization check, distinct from the `require_admin` FastAPI dependency in `auth_services/auth_service.py`).
- `get_pending_approvals`: queries all `Users` with `approval_status == "pending"` (not tenant-scoped in this method — see "Known Limitations" regarding cross-tenant visibility).
- `approve_user` / `reject_user`: validate the target user is currently `"pending"`, update `approval_status`, `approved_by`, `approved_at`, commit, and best-effort send a notification email. On any exception, rolls back via `self.user_repo.rollback()`.

### `user_profile_service.py` — `UserProfileService`
**Responsibility:** Returns the current user's own profile fields (`id`, `name`, `email`, `tenant_id`, `role`, `approval_status`, `created_at`) from an already-authenticated `current_user` object — it does not query the database itself beyond what's passed in.

### `recommended_qa_service.py` — `RecommendedQAService`
**Responsibility:** A **process-local, in-memory** (class-level dict + `threading.Lock`) cache of up to 10 recommended Q&A pairs per tenant, backed by the `RecommendedQA` ORM table.

- `load_all_recommended_questions(db)`: intended to run at server startup; loads all tenants' Q&A into `_tenant_cache`, capped at `MAX_RECOMMENDED_PER_TENANT = 10` per tenant. Also calls `Base.metadata.create_all(...)` scoped to just this one table, effectively self-migrating the table if it doesn't exist.
- `get_recommended_questions`: cache-first; falls back to `_load_tenant` (a DB query) only if the tenant key isn't present and a `db` session was supplied.
- `add_recommended_question` / `delete_recommended_question`: write to DB and then update the in-memory cache to keep it consistent.
- **Multi-instance caveat:** because the cache is a Python class attribute guarded only by a `threading.Lock` (not a distributed lock), this cache is **per-process**. In a multi-worker/multi-pod deployment, writes on one instance will not be reflected in another instance's cache until that instance calls `load_all_recommended_questions` or falls through to `_load_tenant`. Not enough information from the provided code to determine whether other instances ever refresh automatically.

### `llm_runner.py`
**Responsibility:** Bridges the internal `LLMService` singleton (`app.design_pattern.llm_singlton.LLMService`, not provided) into both a plain function call and a LangChain-compatible `LLM` subclass.

- `call_llama(prompt, model_name="llama-3.3-70b-versatile", system_prompt="You are a helpful assistant.", temperature=1.0)`: instantiates `LLMService()` and calls `.generate(...)`. The docstring says it returns a dict with token counts, but a comment notes `generate()` now returns a plain string, and token counts are **not available via this path** — the docstring is stale relative to the current implementation. `model_name` is accepted as a parameter but the comment states the singleton currently uses a fixed model, i.e., **this parameter is currently a no-op** (partially implemented / configuration-dependent on the singleton's own internals, which are not provided).
- `CustomLocalLLM(LLM)`: a LangChain `LLM` implementation with:
  - `_stream`: streams `GenerationChunk`s from `LLMService().generate_stream(prompt)`, forwarding tokens to `run_manager.on_llm_new_token` if present, and caching the last usage dict on the **class** attribute `CustomLocalLLM.last_usage` (again, a process-global, not an instance attribute — concurrent requests would clobber each other's usage stats here; see "Known Limitations").
  - `_call`: non-streaming path via `LLMService().generate(prompt)`, similarly stashing usage on the class attribute.
  - `_llm_type` returns `"groq_llama_stream"`, implying the underlying `LLMService` targets Groq's Llama-hosted inference, though the actual provider integration is not in this package.

### `mlflow_service.py` — `MLflowService`
**Responsibility:** Static-method wrapper around the `mlflow` Python client for experiment tracking across three purposes: query tracking, evaluation, and ingestion.

- Three named experiments: `RAG_Query_Tracking`, `RAG_Evaluation`, `RAG_Data_Ingestion`.
- `log_query_run`: ends any currently-active MLflow run before starting a new/resumed one (defensive against leaked runs), logs `tenant_id`, `model`, `cache_hit` as params, `latency_seconds`, `cost_usd`, `tokens_used` as metrics, and a truncated (500-char) query summary as a JSON artifact. Always calls `mlflow.end_run()` in a `finally` block.
- `log_evaluation_run`, `log_ingest_run`, `log_cost_metrics`: analogous patterns — start run, log params/metrics/artifacts, catch-and-log exceptions (returns `None` on failure rather than raising), always end the run in `finally`.
- `get_experiment_runs`: reads back run history via `mlflow.search_runs`.
- All methods swallow exceptions internally and log them — **MLflow failures never propagate to callers**, which means calling code cannot detect or react to tracking failures; this is a deliberate "observability must not break the request" design, at the cost of silent tracking gaps.

### `rag_services/query_logging_service.py`
**Responsibility:** Celery task `log_query_run_and_cost` plus a non-blocking trigger `trigger_query_logging`.

- Cost formula (hardcoded in code, not configuration): `cost_usd = input_tokens * 0.0000001 + output_tokens * 0.0000002`.
- Writes a `Run` row (via `RunsRepository`) and, if any tokens were used, a `CostLog` row (via `CostLogRepository`).
- After DB writes, performs a **best-effort HTTP POST** to `{API_HOST}/api/internal/metrics/record` (default `API_HOST=http://localhost:8000`) with a 2-second timeout, so the FastAPI process can expose these as Prometheus metrics (the Celery worker itself does not directly expose a `/metrics` endpoint — it round-trips through the API process). Uses `X-Internal-Token` header from `settings.internal_metrics_api_key` if configured. Failures here are caught and logged; they do **not** fail the Celery task.
- On any *other* exception in the task body, retries with exponential backoff (`countdown=min(60 * 2**retries, 600)`), up to the `@shared_task(max_retries=3)` configured retry count.
- `trigger_query_logging`: enqueues onto Celery queue `logging_queue` / routing key `logging`; failures to *enqueue* are caught and only logged, never raised — so a broker outage silently drops logging without impacting the user-facing response.

### `rag_services/agent_logging_service.py`
**Responsibility:** Same pattern as query logging, but for agent runs: `log_agent_run_and_cost` / `trigger_agent_logging`. Adds a `step_count` field and always records `cache_hit=False` (per an inline comment, agent runs are never treated as cached). Same cost formula, same webhook pattern, same queue (`default` routing key here, not `logging_queue`).

### `rag_services/ingest_rag_service.py`
**Responsibility:** Celery task `ingest_file_task` that imports `app.rag.ingest_data_pipline.RAGPipeline` **lazily inside the task** (explicitly to avoid loading heavy dependencies at worker startup) and calls `RAGPipeline.process_file(file_path, custom_metadata, db)` inside a `with get_db_session() as db:` context manager (ensuring the session is closed/rolled back even on exception — this is called out explicitly in the docstring as a deliberate connection-pool-leak prevention measure).
- Retry policy: `autoretry_for=(Exception,)`, `retry_backoff=True`, `max_retries=5`, plus a hard `time_limit=600` / `soft_time_limit=550` (seconds) Celery-level timeout.
- Special-cases `MemoryError` with its own retry (`countdown=60`, `max_retries=3`) distinct from the general exception handler.

### `rag_services/path_processing_service.py` — `PathProcessingService`
**Responsibility:** Factory-pattern dispatcher that picks the right processor (implementation of `PathProcessor`, not provided) for a given file or folder path (`app.design_pattern.upload_factory_pattern.processor_factory`).
- `process_path`: validates the path exists; allows an injected `custom_processor` to override the factory if it can handle the path (`can_handle`); for directories, if `recursive` or `file_extensions` filters were requested, builds a dedicated folder processor via `factory.create_folder_processor(...)`; delegates the actual work to `processor.process(path, tenant_id, source, author, db)`; wraps processor exceptions into a `{"success": False, "error": ...}` dict rather than propagating them.
- A module-level singleton `path_processing_service = PathProcessingService()` is exported for reuse.

### `rag_services/eval_pipline.py`
**Responsibility:** Two Celery tasks for offline RAG evaluation.
- `evaluate_task(tenant_id, path, runs=2, run_id=None)`: wraps `app.rag.evaluation.eval_pipline.EvalPipeline` (not provided). If resuming an existing `run_id`, it defensively checks whether `start_time`/`end_time` params were already logged (to avoid MLflow's "duplicate param" error on retries) and instead tags retries with `mlflow.set_tag`. Computes average retrieval metrics (`precision`, `recall`, `f1`, `mrr`) and generation metrics (`token_f1`) across results, then POSTs them to the same internal metrics webhook pattern seen elsewhere. On failure, logs error tags to MLflow (best-effort) and calls `self.retry(exc=e)`, governed by the task's `retry_kwargs={"max_retries": 3, "countdown": 30}` with `retry_backoff=True` and `retry_jitter=True`.
- `generate_eval_dataset_task(tenant_id, max_chunks=30)`: fetches vector points (`fetch_points`, not provided — implies Qdrant or similar), builds an LLM (`build_llm`) and a QA dataset (`build_dataset`) from them, and writes the result to `app/files/eval_files/{tenant_id}_generated_eval_dataset.json`.

### `episodic_memory_service.py`
**Responsibility:** Celery task `write_episode` that summarizes a list of conversation turns via `app.memory.summarizer.SessionSummarizer` and persists the summary via `app.memory.episodic_memory.EpisodicMemory().save_episode(session_id, summary, user_id, tenant_id, len(turns))`. Retries up to 2 times with a 60-second default delay on failure. `trigger_episode_write` is a no-op if `session_id` or `turns` are empty, and enqueues onto `logging_queue` with routing key `logging`; enqueue failures are logged only, not raised.

### `semantic_memory_service.py`
**Responsibility:** Two Celery tasks:
- `extract_semantic_memory(question, answer, user_id, tenant_id)`: lazily imports `app.memory.memory_extractor.MemoryExtractor` **inside the task body**, with an explicit code comment explaining why: importing it at module load time would create a `route → task → agent → task` circular import, because the extractor depends on agent LLM helpers whose package initialization builds the agent graph. This is a concrete, code-confirmed architectural coupling between the memory subsystem and the (not-provided) agent graph module.
- `prune_low_importance_semantic_memories`: a maintenance task (no retry decorator arguments beyond the bare `@shared_task`) intended to run on a schedule (e.g., nightly — inferred from the docstring "Nightly maintenance task"; the actual Celery Beat schedule is **not provided**), calling `SemanticMemory().prune_low_importance(settings.semantic_memory_prune_importance_below)`.
- `trigger_semantic_memory_extraction`: no-ops on empty question/answer, otherwise enqueues to `logging_queue`/`logging`; enqueue failures logged only.

---

## Request / Task Lifecycle (as evidenced by this package)

This package does not contain the API route definitions or the Agent Graph, so the following flow is reconstructed from the calling conventions visible in the service constructors and the exceptions they raise (all `fastapi.HTTPException`, confirming a FastAPI route caller), plus the Celery task signatures.

### Authentication / Registration flow
```text
POST /auth/register (assumed route, not provided)
  → AuthService.register_user(user_data)
      → UserRepository.find_by_email / create
      → TenantRepository.find_by_name / create
      → hash_service.password_hash
      → token_service.create_access_token
  → returns {access_token, token_type}

Every authenticated request
  → OAuth2PasswordBearer extracts bearer token
  → auth_service.get_current_user(access_token, db)
      → token_service.decode_access_token   (JWTError → 401)
      → UserRepository.find_by_email(email) (missing → 401)
      → approval_status check               (not "approved" → 403)
  → route handler receives `current_user`
  → (optionally) auth_service.require_admin(current_user)  (role != admin → 403)
```

### Invitation flow
```text
Admin: POST /auth/invitations/send
  → InvitationManagementService.send_invitation(...)
      → rate_limit(...)                                  [app.core.rate_limitizer, not provided]
      → InvitationService.send_invitation(...)
          → InvitationRepository checks + create
          → EmailService.send_invitation_email(...)       (best-effort)

Invitee: POST /auth/invitations/register (assumed)
  → InvitationManagementService.register_via_invitation(token, name, password, tenant_id)
      → InvitationService.get_invitation_details(token)
      → hash_service.password_hash(password)
      → InvitationService.accept_invitation_and_register(...)  → user.approval_status = "pending"
      → token_service.create_access_token(...)

Admin: POST /admin/users/{id}/approve  (assumed)
  → UserApprovalService.approve_user(user_id, current_user_id)
      → UserRepository.find_by_id / commit
      → EmailService.send_approval_status_email(...)  (best-effort)
```

### RAG query / agent logging flow (post-response, asynchronous)
```text
Route handler / Agent Graph finishes generating an answer (not provided)
  → trigger_query_logging(...)  OR  trigger_agent_logging(...)
      → Celery apply_async onto "logging_queue" / "logging" routing key (query)
        or "default" / "default" routing key (agent)
      → [worker] log_query_run_and_cost / log_agent_run_and_cost
          → RunsRepository.create(...)
          → CostLogRepository.create(...)      (if tokens > 0)
          → POST {API_HOST}/api/internal/metrics/record   (best-effort, 2s timeout)
```

### Semantic / episodic memory writing (post-response, asynchronous)
```text
Agent Graph finishes a turn (not provided)
  → trigger_semantic_memory_extraction(question, answer, user_id, tenant_id)
      → Celery task extract_semantic_memory
          → MemoryExtractor().extract_and_store(...)     [app.memory, not provided]
  → trigger_episode_write(session_id, turns, user_id, tenant_id)
      → Celery task write_episode
          → SessionSummarizer().summarize(turns, tenant_id)
          → EpisodicMemory().save_episode(...)            [app.memory, not provided]
```

### Ingestion flow
```text
Admin/user uploads a document (route not provided)
  → PathProcessingService.process_path(file_path, tenant_id, source, author, db, ...)
      → processor_factory.get_processor(path)  [design_pattern module, not provided]
      → processor.process(...)
  -- OR, asynchronously --
  → ingest_file_task.apply_async(file_path, tenant_id, source, author)  [Celery]
      → RAGPipeline.process_file(...)          [app.rag, not provided]
```

Not enough information from the provided code to confirm which of these two ingestion paths (synchronous `PathProcessingService` vs. asynchronous `ingest_file_task`) is actually wired to the API layer, or whether both are used for different entry points (e.g., API upload vs. CLI/batch tooling).

---

## Multi-Tenancy

Tenant scoping is enforced at several distinct points in this package, but **not uniformly**:

| Location | Enforcement | Confirmed in code |
|---|---|---|
| JWT claims | `tenant_id` embedded in every access token issued by `AuthService`, `InvitationManagementService`, `TenantRegistrationService` | Yes |
| Invitation creation | Rejects if the invited user already exists **within the same `tenant_id`** | Yes (`invitation_service.py`) |
| Invitation acceptance | Rejects if `invitation.tenant_id != tenant_id` supplied at registration | Yes |
| Recommended Q&A cache | Cache keyed by `str(tenant_id)`; reads/writes/deletes all scoped by tenant key | Yes |
| Semantic/episodic memory tasks | `tenant_id` passed through to `MemoryExtractor`/`EpisodicMemory`, but the isolation mechanism itself lives in `app.memory` (not provided) | Not enough information — isolation logic itself not visible |
| `UserApprovalService.get_pending_approvals` | Queries **all** users with `approval_status == "pending"` across the whole `Users` table, with **no `tenant_id` filter** in this method | Confirmed gap — see Known Limitations |
| Vector DB / retrieval tenant filters | Not provided in this package | Not enough information |

**No cross-tenant isolation mechanism (e.g., row-level security, per-tenant schemas) is implemented in this package beyond explicit `tenant_id` equality filters in application code.** Isolation depends entirely on every caller correctly passing and filtering by `tenant_id`; this package does not show a centralized enforcement layer (e.g., a repository base class that always injects a tenant filter).

---

## Caching

The only cache implemented in this package is `RecommendedQAService`'s per-tenant, per-process, in-memory dictionary (see file-by-file section above). There is:
- No TTL — entries live until process restart or explicit `delete`.
- No semantic cache.
- No exact-match query/answer cache for RAG responses in this package (query/agent logging records `cache_hit` as a boolean field, implying a cache exists somewhere in the request path — but the cache implementation itself, and what a cache hit skips, is **not provided**).

---

## Async / Background Processing (Celery)

All background work in this package uses Celery, via either `@shared_task` (implicit app binding) or `@celery_app.task` (explicit import of `app.celery.celery_config.celery_app`) decorators. The Celery app configuration itself (broker, backend, queue definitions, worker concurrency) is **not provided**.

| Task | Decorator / Retry Policy | Queue / Routing Key |
|---|---|---|
| `log_query_run_and_cost` | `@shared_task(bind=True, max_retries=3, default_retry_delay=60)`, plus custom exponential backoff up to 600s | `logging_queue` / `logging` |
| `log_agent_run_and_cost` | same as above | `default` / `default` |
| `write_episode` | `@shared_task(bind=True, max_retries=2, default_retry_delay=60)` | `logging_queue` / `logging` |
| `extract_semantic_memory` | `@shared_task(bind=True, max_retries=2, default_retry_delay=60)` | `logging_queue` / `logging` |
| `prune_low_importance_semantic_memories` | `@shared_task` (no retry config shown) | Not specified — no `apply_async` call in this package; presumably scheduled via Celery Beat (not provided) |
| `ingest_file_task` | `@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5}, time_limit=600, soft_time_limit=550)` | Not specified in this file |
| `evaluate_task` | `@celery_app.task(bind=True, auto_retry_for=(Exception,), retry_kwargs={"max_retries": 3, "countdown": 30}, retry_backoff=True, retry_jitter=True)` | Not specified |
| `generate_eval_dataset_task` | same pattern as `evaluate_task` | Not specified |

**Design pattern observed:** every "trigger" function (`trigger_query_logging`, `trigger_agent_logging`, `trigger_episode_write`, `trigger_semantic_memory_extraction`) wraps `apply_async` in a `try/except` that only logs on failure — meaning a Celery broker outage will silently drop logging/memory-writing work without ever raising to the caller. This is a deliberate "never let observability/memory-writing break the user-facing response" design choice, consistently applied.

---

## Observability

- **MLflow** (`mlflow_service.py`): three experiments (`RAG_Query_Tracking`, `RAG_Evaluation`, `RAG_Data_Ingestion`); logs params (tenant_id, model, cache_hit, dataset_size, etc.), metrics (latency, cost, tokens, precision/recall/f1/mrr/token_f1), and JSON artifacts (query summaries, ingestion info, full eval results).
- **Prometheus, via internal webhook**: `query_logging_service.py`, `agent_logging_service.py`, and `eval_pipline.py` each independently POST a metrics payload to `{API_HOST}/api/internal/metrics/record` (default `API_HOST=http://localhost:8000`) after completing their primary work. This implies Celery workers don't expose `/metrics` themselves; instead they push to the API process, which is presumably scraped by Prometheus (not provided). Auth to that internal endpoint is an optional `X-Internal-Token` header from `settings.internal_metrics_api_key`.
- **Python `logging`**: used pervasively (`logger.info/warning/error`) across every service; no structured/JSON logging format or request-ID propagation is visible in this package.
- **Cost tracking**: computed inline in `query_logging_service.py` and `agent_logging_service.py` with a hardcoded linear formula per input/output token; not configurable per model in this package (despite `model_name` being a parameter/field, it is not used in the cost formula itself).

---

## Security

**Implemented:**
- Password hashing via Argon2 (default) / bcrypt (legacy) through `passlib`.
- JWT-based bearer auth (`HS256`), with a startup-time hard failure if no secret key is configured (`token_service.py`) — good practice, no silent insecure default.
- Server-side re-validation of `approval_status` on every request (not just at login), so revoking a user's approval takes effect immediately without needing token revocation.
- Admin-only gating via `require_admin` (FastAPI dependency) and `UserApprovalService.authorize_admin` (manual check) — **two different mechanisms**, used in different services; there is no single shared authorization utility visible across the whole package.
- Invitation tokens are generated with `secrets.token_hex(32)` (cryptographically secure, 256 bits of entropy) and expire after 7 days.
- Internal-only metrics endpoint gated by an optional shared-secret header (`X-Internal-Token`).

**Not implemented / not visible in the provided code:**
- Prompt-injection defenses — nothing in this package inspects or sanitizes LLM inputs/outputs.
- Rate limiting logic itself (`app.core.rate_limitizer.rate_limit` is called but not defined here) — only its call site is visible.
- Row-level or database-level tenant isolation — tenant scoping is entirely dependent on application code passing the right `tenant_id` filters (see Multi-Tenancy section; `UserApprovalService.get_pending_approvals` is a confirmed gap).
- JWT refresh-token flow — only access tokens (60-minute expiry, non-renewable in this package) are issued.
- Secrets are never logged directly in the reviewed code, but `email_service.py`'s dev-mode fallback **does log full email bodies, including invitation tokens**, at `WARNING` level when SMTP credentials are unset — a real credential/token could leak into logs in a misconfigured non-dev environment.

---

## Error Handling

Consistent pattern across HTTP-facing services (`AuthService`, `InvitationService`, `InvitationManagementService`, `TenantRegistrationService`, `UserApprovalService`, `UserProfileService`):
- Expected validation failures → specific `HTTPException` with 4xx status and a descriptive `detail`.
- Unexpected exceptions → caught, logged with `logger.error`, re-raised as generic `500 HTTPException`.
- Where a DB session mutation was in progress, the exception handler calls `.rollback()` before re-raising (`TenantRegistrationService`, `UserApprovalService`).
- Non-critical side effects (sending email) are **always** wrapped in their own inner `try/except` that only logs — a failed welcome/invitation/approval email never fails the primary operation.

Celery tasks follow a different pattern: catch broad `Exception`, log, and call `self.retry(...)` (or raise `self.retry(...)`, which re-raises the retry-triggering exception) so Celery's retry machinery takes over, up to each task's configured `max_retries`. `ingest_file_task` additionally special-cases `MemoryError` with its own retry policy separate from generic exceptions.

---

## External Dependencies

| Dependency | Purpose | Where Used | Required? |
|---|---|---|---|
| PostgreSQL (via SQLAlchemy `Session`) | Primary relational store: users, tenants, invitations, runs, cost logs, recommended Q&A | Nearly every service | Yes |
| Redis / message broker (implied by Celery) | Task queue backend for all `@shared_task`/`@celery_app.task` functions | All `rag_services/*`, `episodic_memory_service.py`, `semantic_memory_service.py` | Yes (broker config not shown, but Celery usage is pervasive) |
| MLflow tracking server | Experiment/run/metric/artifact logging | `mlflow_service.py`, `rag_services/eval_pipline.py` | Yes for observability, but failures are swallowed so not required for core function |
| SMTP server | Transactional email | `email_service.py` | No — has an explicit dev-mode fallback that logs instead of sending |
| Internal FastAPI `/api/internal/metrics/record` endpoint | Bridges Celery-worker metrics into the API process for Prometheus scraping | `query_logging_service.py`, `agent_logging_service.py`, `eval_pipline.py` | No — best-effort, 2s timeout, failure only logged |
| LLM backend behind `LLMService` singleton (implies Groq-hosted Llama, per `_llm_type = "groq_llama_stream"`) | Text generation | `llm_runner.py` | Yes, for any LLM-dependent feature |
| Vector DB (implied — "Qdrant" appears as a default string parameter in `mlflow_service.py`'s `log_ingest_run`, and `eval_pipline.py`'s `fetch_points` implies a vector store) | Retrieval / eval dataset generation | `rag_services/eval_pipline.py` (indirectly) | Not enough information from this package alone to confirm which vector DB is used in production; only inferred from a default parameter value and an unprovided `fetch_points` function |

---

## Configuration

Environment variables and settings fields referenced (via `app.core.config.settings`), values never shown/assumed:

```env
API_SECRET_KEY=<your-jwt-signing-secret>        # required — token_service.py raises RuntimeError at import if unset
SMTP_USERNAME=<smtp-username>                    # optional — falls back to dev-mode logging if unset
SMTP_PASSWORD=<smtp-password>                    # optional — see above
SMTP_SERVER=<smtp-host>
SMTP_PORT=<smtp-port>
EMAIL_FROM=<from-address>
FRONTEND_URL=<frontend-base-url>                 # used to build invitation registration links
INTERNAL_METRICS_API_KEY=<shared-secret>          # optional — sent as X-Internal-Token to the internal metrics webhook
SEMANTIC_MEMORY_PRUNE_IMPORTANCE_BELOW=<threshold>  # used by prune_low_importance_semantic_memories
API_HOST=http://localhost:8000                    # environment variable (os.environ), not a `settings` field — default shown is the code's literal default
```

`ACCESS_TOKEN_EXPIRE_MINUTES = 60`, `TOKEN_EXPIRY_DAYS = 7` (invitations), `MAX_RECOMMENDED_PER_TENANT = 10` are hardcoded module-level constants, not environment-configurable in this package.

Not enough information from the provided code to enumerate the full `Settings` class (e.g., database URL, Redis/broker URL, Qdrant URL, LLM API keys) — only the fields actually referenced by name in this package are listed above.

---

## Cost Considerations

Per query/agent run, the only cost computation visible in this package is:

```text
cost_usd = input_tokens * 0.0000001 + output_tokens * 0.0000002
```

applied uniformly regardless of `model_name` (the parameter is recorded alongside cost but not used in the formula). This runs unconditionally whenever `log_query_run_and_cost` / `log_agent_run_and_cost` executes and `input_tokens or output_tokens > 0`. No per-embedding-call or per-reranking-call cost tracking exists in this package (those pipeline stages are not provided).

---

## Failure Scenarios

| Failure | Expected Behavior (as coded) | Impact |
|---|---|---|
| SMTP unavailable / not configured | `EmailService.send_email` catches the exception (or, if credentials are simply unset, never attempts SMTP) and returns `False`; callers only log the failure | Emails silently not sent; primary operation (registration, approval, invitation) still succeeds |
| Celery broker unavailable | Every `trigger_*` function's `apply_async` call is wrapped in `try/except` that only logs | Logging, memory-writing, and ingestion triggers silently fail to enqueue; no retry, no user-facing error |
| Database failure inside an HTTP-facing service | Caught, `rollback()` called where a session mutation was open, re-raised as `500 HTTPException` | Request fails with a generic 500; DB left in a consistent state due to rollback |
| Database failure inside a Celery task | Caught by the task's broad `except Exception`, task retries per its configured policy (2–5 retries with backoff, depending on task) | Task eventually gives up after max retries; Celery's dead-letter/failure behavior beyond that is not shown |
| MLflow unavailable | Every `MLflowService` method catches the exception internally and logs it; `finally: mlflow.end_run()` still runs (itself wrapped or not, depending on method) | No metrics recorded for that run; caller is never informed and receives `None` from some methods |
| Internal metrics webhook unavailable/slow | `requests.post(..., timeout=2.0)` wrapped in `try/except`, logged only | No Prometheus metrics for that run; Celery task still completes/commits its DB writes |
| Invalid/expired JWT | `decode_access_token` raises `JWTError`, caught in `get_current_user`, re-raised as `401` | Request rejected before reaching route logic |
| User approval revoked mid-session | Next request re-checks `approval_status` in `get_current_user` and returns `403` | Effectively immediate access revocation without needing token blacklisting |

---

## Testing

No test files were provided in the analyzed code (`services.zip` contains only the `services` package and its compiled `__pycache__` artifacts, no `tests/` directory).

---

## Deployment

Deployment configuration (Dockerfiles, `docker-compose`, environment files, Celery worker startup commands, health checks) is **not provided** in this package. What can be inferred:
- Celery workers must import this package's task modules to register tasks with the app defined in `app.celery.celery_config.celery_app`.
- The webhook-based metrics bridge implies Celery workers and the FastAPI API process are expected to run as separate processes/containers that can reach each other over HTTP (`API_HOST` environment variable, defaulting to `http://localhost:8000`, with an inline comment referencing `host.docker.internal` for Prometheus reaching the host from Docker — implying at least one deployment topology involves Docker).

---

## Known Limitations

### Confirmed Limitations
- `UserApprovalService.get_pending_approvals` queries pending users across **all tenants**, with no `tenant_id` filter — a cross-tenant data-visibility gap if this method's caller doesn't apply its own filter (not shown in this package).
- `RecommendedQAService`'s cache is process-local; multi-instance deployments will see stale/inconsistent cache state between writes and the next full reload.
- `CustomLocalLLM.last_usage` is stored as a **class attribute**, not an instance/request-scoped value — concurrent LLM calls will race and can report incorrect token usage for a given request.
- `EmailService`'s dev-mode fallback logs full email bodies (including invitation tokens) when SMTP credentials are unset — a token-leakage risk if this code path is ever hit outside local development.
- Cost calculation uses a hardcoded, model-agnostic linear formula; it does not vary by `model_name` despite the parameter being present and stored.
- `llm_runner.call_llama`'s `model_name` parameter is accepted but, per an inline comment, not actually used by the underlying singleton — a misleading API surface.
- Two independent, non-shared admin-authorization mechanisms exist (`require_admin` FastAPI dependency vs. `UserApprovalService.authorize_admin` manual check), increasing the chance of an inconsistent check being used somewhere.

### Potential Risks / Improvements
- Centralize tenant-scoping (e.g., a repository base class or query helper that always requires/injects `tenant_id`) to reduce the risk of gaps like the one in `get_pending_approvals`.
- Replace the process-local recommended-Q&A cache and `CustomLocalLLM.last_usage` class attribute with a shared cache (e.g., Redis) or properly request-scoped state, especially in multi-worker deployments.
- Make SMTP fallback behavior environment-aware (e.g., only log bodies when `ENV=development`) to avoid accidental token leakage.
- Consider a shared authorization utility to unify admin-role checks across services.
- Cost formula could be extended to look up per-model pricing rather than a single hardcoded rate.

---

## Summary

This package implements the multi-tenant auth/onboarding layer (registration, invitations, approval, JWT issuance/validation) and a set of Celery-driven background services that keep the user-facing request path fast: query/agent-run logging with cost accounting and a Prometheus-webhook bridge, MLflow experiment tracking, RAG ingestion/evaluation task wrappers, and asynchronous episodic/semantic memory writing. The consistent architectural pattern throughout is **"never let a secondary concern (email, logging, metrics, memory writing) fail the primary request"** — every non-critical side effect is independently try/excepted and only logged on failure. The main structural risks visible in this package are process-local caches/state that won't scale correctly across multiple instances, and one confirmed tenant-isolation gap in the admin-approval listing method. The Agent Graph, RAG retriever/reranker, vector database client, and memory-store implementations that this package's Celery tasks call into are referenced throughout but were not included in the provided code, so their internal behavior could not be documented here.