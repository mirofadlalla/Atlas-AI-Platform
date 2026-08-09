# Atlas AI — Repositories Module

## Overview

This module (`app/repositories`) is the **data access layer** for Atlas AI: a set of thin repository classes wrapping SQLAlchemy `Session` queries for each ORM model (`Users`, `Tenants`, `Runs`, `CostLog`, `Invitation`, `TRACKER_DB_FILE`, `MemoryEpisode`), plus one repository (`QdrantRepository`) wrapping the Qdrant vector database client for hybrid dense+sparse semantic search.

**Important note on sources:** A `README.md` ships inside the provided archive, but its code samples do **not** match the actual repository implementations in several places (different method names, different constructor signatures, different model field names, and in the case of `QdrantRepository`, an entirely different and non-functional example implementation with an undefined `query_text` variable and a stubbed `delete_by_tenant`). This documentation describes **only what the actual `.py` files implement**, and calls out the specific discrepancies from the bundled README separately so they aren't mistaken for current behavior.

## Responsibilities

- Provide CRUD and query methods for each SQLAlchemy model, scoped to a single `Session` instance passed into each repository's constructor.
- Wrap Qdrant vector-store operations: collection creation, payload-index management, hybrid (dense + sparse) document upserts with deduplication, and raw dense-vector search.
- Implement the "find existing / insert or update" upsert pattern for episodic memory (`EpisodeRepository.save_episode`).
- Provide tenant-scoped and cross-table aggregate queries (cost summaries, run statistics) via SQLAlchemy `func` aggregates and joins.

## Boundaries — what this module does not do

- It does not define the ORM models themselves (imported from `app.models.*`, not included in this archive).
- It does not manage transactions/session lifecycle beyond calling `commit()`/`flush()`/`refresh()`/`rollback()` on the `Session` it's given — session creation/closing is the caller's responsibility (likely `app.core.db`, not provided).
- It does not perform authentication/authorization — callers are expected to have already resolved and validated `tenant_id`/`user_id`.
- **No repository in this archive enforces tenant isolation automatically or by base-class contract** — each method must explicitly include a `tenant_id` filter where relevant, and some methods (see Multi-Tenancy below) do not.

## Dependencies

- `sqlalchemy.orm.Session`, `sqlalchemy.func` (aggregates).
- `app.models.*` (Users, Tenants, Runs, CostLog, Invitation, TRACKER_DB_FILE, MemoryEpisode) — not included in this archive, only imported.
- `app.core.config.settings` — not included in this archive; `EpisodeRepository` reads `settings.episodic_memory_ttl_days` and `settings.episodic_memory_recent_limit`; `QdrantRepository` reads `settings.qdrant_url` and `settings.sparse_embedding_model`.
- `qdrant_client` (`QdrantClient`, `VectorParams`, `Distance`, `SparseVectorParams`, `PointStruct`, `PayloadSchemaType`).
- `fastembed.SparseTextEmbedding` (BM25-style sparse embedding model).
- `app.design_pattern.embedded_model.EmbeddedModel` — not included in this archive; used as the dense embedding model, instantiated as a process-wide singleton.

## What depends on this module

Not enough information from the provided code — no callers (route handlers, service classes) are included in this archive. The bundled README's "Usage Example" section shows a hypothetical FastAPI route calling `RunsRepository`, but its `create_run`/`update_run` method signatures do not match the actual `RunsRepository.create`/`update` implementations (see Documentation Fidelity Notes below), so it should not be treated as accurate usage documentation.

## Project Structure

```text
repositories/
├── README.md                          # Bundled docs — contains stale/fictional examples, see notes below
├── cost_log_repository.py             # CostLogRepository — CRUD + cost aggregation, joins Runs for tenant scoping
├── episode_repository.py              # EpisodeRepository — upsert + recency-windowed reads for episodic memory
├── invitation_repository.py           # InvitationRepository — CRUD + accept/reject/expire lifecycle
├── qdrant.py                          # QdrantRepository — Qdrant collection mgmt, hybrid upsert, dense search
├── runs_repository.py                 # RunsRepository — CRUD + per-tenant stats for agent run records
├── tenant_repository.py               # TenantRepository — minimal tenant CRUD, explicit flush/commit/rollback
├── trakcer_db_file_repositorie.py     # TrackerDBFileRepository — file ingestion dedup/status tracking (note: filename typo in repo)
└── user_repository.py                 # UserRepository — user lookup/creation, explicit flush/commit/rollback
```

## How It Works — Architecture

```text
                (not provided — route/service layer)
                             │
                             ▼
        ┌──────────────────────────────────────┐
        │           Repository Layer             │
        │  (this module — one class per model)    │
        └───────────────┬──────────────┬─────────┘
                         │              │
                         ▼              ▼
              SQLAlchemy Session   QdrantClient
              (app.core.db,         (Qdrant vector DB,
               not provided)         via app.core.config.settings)
                         │
                         ▼
                   PostgreSQL (or configured RDBMS)
```

Each SQL-backed repository follows the same shape: `__init__(self, db: Session)` stores the session; methods build a `db.query(Model)...` chain, then either `.first()`/`.all()`/`.scalar()`-style reads, or `db.add(obj); db.commit()` (sometimes followed by `db.refresh(obj)`) for writes. `QdrantRepository` is structurally different — it holds a `QdrantClient` plus two shared embedding-model singletons and exposes collection/point-level operations instead of ORM queries.

## File-by-File Reference

### `user_repository.py` — `UserRepository`

| Method | Behavior |
|---|---|
| `find_by_email(email)` | `db.query(Users).filter(Users.email == email).first()` — **no tenant filter**; relies on `email` being globally unique (per the `Users` model's `unique=True` constraint) |
| `find_by_email_and_tenant(email, tenant_id)` | Same lookup, additionally filtered by `tenant_id` |
| `find_by_id(user_id)` | `db.query(Users).filter(Users.id == user_id).first()` — **no tenant filter** |
| `create(name, email, hashed_password, tenant_id, role="user", approval_status="approved")` | Constructs a `Users` row (explicitly sets `approved_by=None`, `approved_at=None`), calls `db.add()` + `db.flush()` (not `commit()`) — caller must commit |
| `commit()` / `rollback()` | Thin pass-throughs to the underlying session |

### `tenant_repository.py` — `TenantRepository`

| Method | Behavior |
|---|---|
| `find_by_name(name)` | Query `Tenants` by exact name match |
| `find_by_id(tenant_id)` | Query `Tenants` by id |
| `create(name, plan="starter")` | Constructs and adds a `Tenants` row, calls `db.flush()` only (not commit) |
| `commit()` / `rollback()` | Pass-throughs |

Note: default plan value here is `"starter"`, differing from the `Tenants` model's own column default described in the bundled model README (`"free"`) — this repository's default is what actually applies if `plan` isn't passed explicitly by the caller.

### `runs_repository.py` — `RunsRepository`

| Method | Behavior |
|---|---|
| `create(tenant_id, query, answer, latency, cache_hit=False, retrieved_docs_ids="")` | Builds a `Runs` row using the model's actual fields (`query`, `answer`, `latency`, `cache_hit`, `retrieved_docs_ids`); commits and refreshes |
| `get_by_id(run_id)` | Filters `Runs.run_id == run_id` |
| `get_by_tenant(tenant_id, limit=100, offset=0)` | Filters by `tenant_id`, orders by `created_at desc`, paginated |
| `get_stats_for_tenant(tenant_id)` | Aggregates `count(run_id)` as `total_runs`, `avg(latency)`, `sum(cache_hit)` as `cache_hits`, filtered by tenant |
| `update(run_id, **kwargs)` | Generic attribute setter — only sets keys that already exist as attributes (`hasattr` check) — then commits/refreshes |
| `delete(run_id)` | Deletes by id if found, returns bool |

The bundled README's `RunsRepository.create_run`/`update_run` examples reference `question`, `final_answer`, `status`, `total_tokens`, `total_cost_usd`, `started_at`, `completed_at` — **none of these fields exist on the actual `Runs` model or repository**. The real model/repository use `query`/`answer`/`latency`/`cache_hit`/`retrieved_docs_ids` instead. Treat the bundled README's Runs examples as outdated/aspirational.

### `cost_log_repository.py` — `CostLogRepository`

| Method | Behavior |
|---|---|
| `create(run_id, input_tokens, output_tokens, model_name, cost_usd)` | Builds a `CostLog` row, casting `cost_usd` to `Decimal(str(cost_usd))` for numeric precision; commits and refreshes |
| `get_by_id(log_id)` | Filters `CostLog.log_id == log_id` |
| `get_by_run_id(run_id)` | Filters `CostLog.run_id == run_id`, returns a **single** object (`.first()`) even though the model docstring states one run may have many cost entries — callers needing all entries for a run would need a different method (not present) |
| `get_cost_summary_for_tenant(tenant_id)` | Joins `CostLog` to `Runs` (implicit join via `.join(Runs)`, relying on the FK), aggregates total/avg cost, request count, total input/output tokens, filtered by `Runs.tenant_id` |
| `get_cost_by_model(tenant_id)` | Same join pattern, grouped by `model_name`, returns a dict keyed by model name |
| `update(log_id, **kwargs)` | Generic `hasattr`-gated attribute setter, commits/refreshes |
| `delete(log_id)` | Deletes by id if found |

Tenant scoping for cost queries is achieved entirely via the `CostLog → Runs` join and filtering on `Runs.tenant_id`, since `CostLog` itself does not carry its own `tenant_id` column in the actual model (unlike what the bundled README's `CostLog` model example shows — that example includes a direct `tenant_id` FK on `CostLog`, which is not present in the real model based on the join pattern this repository relies on).

### `invitation_repository.py` — `InvitationRepository`

| Method | Behavior |
|---|---|
| `create(invited_email, invited_by, tenant_id, token, expires_at)` | Builds an `Invitation` row (note: real model class is `Invitation`, singular — the bundled README's examples reference `Invitations`, plural, which does not match); commits and refreshes |
| `get_by_id(invitation_id)` | Filters `Invitation.invitation_id == invitation_id` |
| `get_by_token(token)` | Filters `Invitation.token == token` |
| `get_by_email(email, status=None)` | Filters by `invited_email`, optional additional `status` filter, returns a list |
| `get_pending_for_tenant(tenant_id)` | Filters by `tenant_id` and `status == "pending"`, ordered by `created_at desc` |
| `get_sent_by_admin(admin_id, status=None)` | Filters by `invited_by == admin_id`, optional `status` filter |
| `accept_invitation(token, user_id)` | Looks up by token, checks `invitation.is_valid()` (a method on the `Invitation` model, not provided in this archive but referenced), sets `status="accepted"`, `user_id`, `accepted_at`, commits |
| `reject_invitation(token)` | Sets `status="rejected"`, commits |
| `expire_invitation(invitation_id)` | Sets `status="expired"`, commits |
| `delete(invitation_id)` | Deletes by id if found |

Note: `accept_invitation`/`reject_invitation`/`expire_invitation` use `datetime.utcnow()` (naive) to set `accepted_at`, while the `Invitation` model (per the models module documentation) stores `created_at`/`expires_at`/`accepted_at` as timezone-aware columns — a naive/aware datetime mismatch is possible here, though this cannot be fully confirmed without the model's column definitions being re-inspected in this exact archive.

### `episode_repository.py` — `EpisodeRepository`

| Method | Behavior |
|---|---|
| `save_episode(session_id, summary, user_id, tenant_id, raw_turns, ttl_days=None)` | **Upsert pattern**: looks up the most recent `MemoryEpisode` matching `(session_id, user_id, tenant_id)`; if found, updates `summary`/`raw_turns`/`expires_at` in place; if not found, inserts a new row. `ttl_days` defaults to `settings.episodic_memory_ttl_days` if not passed. Commits and refreshes either way. |
| `get_recent(user_id, tenant_id, limit=None, exclude_session_id=None)` | Filters by `user_id`, `tenant_id`, and `expires_at > now` (i.e., only non-expired episodes), optionally excludes a given session, orders by `created_at desc`, limited by `limit` or `settings.episodic_memory_recent_limit` |
| `clear_user(user_id, tenant_id)` | Bulk deletes all episodes for a user within a tenant via `.delete(synchronize_session=False)`, commits, returns count deleted |

This is the only repository in this archive implementing TTL-aware filtering directly in the query (`expires_at > now`), rather than relying on a separate expiry/cleanup job.

### `trakcer_db_file_repositorie.py` — `TrackerDBFileRepository`

(Filename as shipped in the archive contains a typo — `trakcer_db_file_repositorie.py` — documented here as-is, not corrected.)

| Method | Behavior |
|---|---|
| `add_processed_file(tenant_id, file_name, file_hash)` | Inserts a new `TRACKER_DB_FILE` row with default status (model default is `"completed"`, per the models module); commits and refreshes |
| `is_file_processed(tenant_id, file_hash)` | Returns `True` only if a record exists with matching `tenant_id`+`file_hash` **and** `status == "completed"` — records stuck in `"processing"` or `"failed"` are treated as not-processed, allowing reprocessing |
| `mark_processing(tenant_id, file_name, file_hash)` | Looks up an existing record by `(tenant_id, file_hash)`; if none exists, creates one with `status="processing"` and `started_at=utcnow()`; if one exists, updates it in place to `"processing"` with a fresh `started_at` (this will silently overwrite a previously `"completed"` or `"failed"` record's status) |
| `mark_completed(tenant_id, file_hash)` | Looks up the existing record; if found, sets `status="completed"`, `completed_at`/`processed_at` timestamps; if no record is found, this is a silent no-op (returns `None`) |
| `mark_failed(tenant_id, file_hash)` | Same lookup pattern, sets `status="failed"` and `completed_at`; silent no-op if no record found |

This is the module's implementation of the ingestion-dedup mechanism described at a high level in the `TRACKER_DB_FILE` model's docstring (SHA-256 hash comparison to avoid reprocessing).

### `qdrant.py` — `QdrantRepository` and module-level helpers

This file is structurally different from the SQL repositories: it wraps a `QdrantClient` rather than a SQLAlchemy `Session`, and manages two process-wide singleton embedding models via module-level globals.

| Function/Method | Behavior |
|---|---|
| `get_shared_dense_model()` | Lazily instantiates and caches a module-global `EmbeddedModel()` (not provided) — a singleton shared across all `QdrantRepository` instances in the process |
| `get_shared_sparse_model()` | Lazily instantiates and caches a module-global `SparseTextEmbedding(model_name=settings.sparse_embedding_model)` (from `fastembed`) — same singleton pattern |
| `QdrantRepository.__init__(url=None)` | Creates a `QdrantClient(url=url or settings.qdrant_url)`; assigns `self.dense_model`/`self.sparse_model` from the two shared singletons above |
| `create_collection(collection_name, vector_size=1024)` | If the collection doesn't exist, calls `client.recreate_collection` with **named vectors**: a `"dense"` vector (cosine distance, configurable size) and a `"sparse"` vector (`SparseVectorParams`) — i.e., hybrid dense+sparse is a first-class collection schema feature, not bolted on. Always calls `ensure_payload_indexes` afterward (idempotent) regardless of whether the collection was just created |
| `ensure_payload_indexes(collection_name)` | Creates KEYWORD payload indexes on six nested filter fields (`payload.tenant_id`, `payload.file_type`, `payload.department`, `payload.language`, `payload.source`, `payload.author`) reflecting the payload shape produced by `add_hybrid_documents` (`{"content": ..., "payload": {...metadata...}}`). Each index creation is individually try/excepted — a failure on one field logs a warning but does not stop the others or raise |
| `ensure_semantic_memory_indexes(collection_name=SEMANTIC_MEMORY_COLLECTION)` | Creates a **different** set of indexes (`tenant_id`, `user_id`, `memory_type` as KEYWORD, `importance` as FLOAT) on **top-level** (non-nested) payload fields — implying the semantic-memory collection uses a flatter payload shape than the document-chunk collection. Unlike `ensure_payload_indexes`, this method does **not** wrap each call in try/except — an exception here will propagate |
| `add_hybrid_documents(collection_name, documents)` | Deduplicates by point `id` before embedding: retrieves existing point IDs from Qdrant (`client.retrieve`, `with_payload=False, with_vectors=False`), filters `documents` down to only those whose `id` isn't already present, and **skips embedding entirely** if nothing is new (an explicit resource-saving optimization). For genuinely new documents, generates both dense (`self.dense_model.embed_documents`) and sparse (`self.sparse_model.embed`) vectors, builds `PointStruct`s with the nested `{"content", "payload"}` shape, and `upsert`s them. Note: if the initial `client.retrieve` call raises, the exception is caught and `existing_ids` is set to an empty set — meaning **all** documents would then be treated as new (potential redundant re-embedding on retrieval failure, but not lost data) |
| `delete_collection(collection_name)` | Deletes the collection if it exists, else logs a no-op message |
| `list_collections()` | Returns a list of collection name strings |
| `search(collection_name, query_vector, top_k=5)` | Plain dense-vector similarity search via `client.search(...)` — **does not** combine dense+sparse or apply reranking; this is a single-vector search method distinct from any hybrid retrieval logic |
| `get_all_points(collection_name)` | Retrieves all points with payload (no vectors) — explicitly documented as for debugging/evaluation use; catches and logs any exception, returning an empty list on failure |

**Important discrepancy:** The bundled `README.md`'s `QdrantRepository.search_hybrid` example (dense + sparse + rerank + tenant post-filter) is **not implemented anywhere in the actual `qdrant.py` file**. The real file has no `search_hybrid` method, no `_search_dense`/`_search_sparse`/`_merge_results`/`_rerank` helpers, and no `upsert_documents`/`delete_by_tenant` methods as shown in the README. The actual hybrid-search *ingestion* path (`add_hybrid_documents`) is implemented and functional; the actual hybrid-search *query* path is not present in this archive — only single-vector `search()` is. If a hybrid query-time search exists elsewhere in Atlas AI, it is **not included in this archive**.

## Multi-Tenant Data Isolation

### Enforced (tenant filter present)

- `UserRepository.find_by_email_and_tenant` — explicit.
- `RunsRepository.get_by_tenant`, `get_stats_for_tenant`.
- `CostLogRepository.get_cost_summary_for_tenant`, `get_cost_by_model` — enforced via join to `Runs.tenant_id`, since `CostLog` has no direct tenant column reachable in this repository.
- `InvitationRepository.get_pending_for_tenant`.
- `EpisodeRepository.save_episode`, `get_recent`, `clear_user` — all filter by both `tenant_id` and `user_id`.
- `TrackerDBFileRepository` — every method takes and filters by `tenant_id`.
- `QdrantRepository.ensure_payload_indexes`/`ensure_semantic_memory_indexes` — index `tenant_id` as a filterable field, implying tenant filtering happens at **query time** by whatever calls `client.search`/`client.query` with a tenant filter — but the provided `search()` method itself takes no `tenant_id` parameter and applies no tenant filter internally. **Tenant isolation for Qdrant search is therefore not enforced inside this repository's `search()` method** — it must be applied by the caller constructing the query filter, which is not shown in this archive.

### Not enforced (no tenant filter — lookup by unique/global key only)

- `UserRepository.find_by_email` — looks up across all tenants by email alone (relies on email global uniqueness at the DB level).
- `UserRepository.find_by_id` — no tenant check; a caller passing an arbitrary `user_id` gets that user regardless of tenant.
- `TenantRepository.find_by_id`/`find_by_name` — tenant lookup itself is naturally not tenant-scoped (you're looking *for* the tenant).
- `RunsRepository.get_by_id` — no tenant check on a single run lookup by id.
- `CostLogRepository.get_by_id`/`get_by_run_id` — no tenant check.
- `InvitationRepository.get_by_id`/`get_by_token` — no tenant check (token lookups are inherently keyed by the unique token, which is reasonable for an invitation-acceptance flow, but `get_by_id` has no such justification visible in this code).

This split matches a common (and reasonable) repository pattern where single-record lookups by a globally-unique key (email, token, primary id) are intentionally tenant-agnostic, while list/aggregate queries are tenant-scoped — but it does mean **callers must not treat every repository method as automatically tenant-safe**. The bundled README's claim that "all queries automatically filtered by tenant_id" is not accurate for this actual code; several methods explicitly are not.

## Data Flow — Key Operations

```text
Episodic memory write (episode_repository.save_episode):
  (session_id, user_id, tenant_id) → lookup latest matching MemoryEpisode
      found?  → update summary/raw_turns/expires_at in place
      not found? → insert new MemoryEpisode(expires_at = now + ttl_days)
  → commit + refresh → MemoryEpisode object returned

Hybrid document ingestion (qdrant.add_hybrid_documents):
  documents[] → extract ids → client.retrieve(existing ids)
      → filter to new_documents (id not in existing_ids)
      → if none new: skip (log + return)
      → dense_model.embed_documents(texts), sparse_model.embed(texts)
      → build PointStruct(id, payload={content, payload: metadata}, vector={dense, sparse})
      → client.upsert(collection_name, points)

Cost aggregation (cost_log_repository.get_cost_summary_for_tenant):
  tenant_id → CostLog JOIN Runs ON CostLog.run_id == Runs.run_id
      → filter Runs.tenant_id == tenant_id
      → aggregate SUM/AVG/COUNT over CostLog columns
      → returned as a plain dict with float-cast Decimal values
```

## External Dependencies

| Dependency | Purpose | Where Used | Required? |
|---|---|---|---|
| PostgreSQL (or configured RDBMS) via SQLAlchemy `Session` | Backing store for all non-Qdrant repositories | All files except `qdrant.py` | Required |
| Qdrant | Vector storage for hybrid dense+sparse document search and semantic memory | `qdrant.py` | Required for retrieval/semantic-memory features |
| `fastembed` (`SparseTextEmbedding`) | Sparse (BM25-style) embedding generation | `qdrant.py` | Required for `add_hybrid_documents` |
| `app.design_pattern.embedded_model.EmbeddedModel` | Dense embedding generation | `qdrant.py` (not provided — only its call interface, `embed_documents`, is visible) | Required for `add_hybrid_documents` |
| `app.core.config.settings` | `qdrant_url`, `sparse_embedding_model`, `episodic_memory_ttl_days`, `episodic_memory_recent_limit` | `qdrant.py`, `episode_repository.py` | Required |
| `app.models.*` | ORM model classes | All SQL repository files | Required |

## Configuration

No configuration is defined in this module itself. It consumes configuration values sourced from the not-provided `app.core.config.settings` object:

```env
# Consumed via settings.* attribute access — exact env var names not visible in this archive
QDRANT_URL=<your-qdrant-url>                 # settings.qdrant_url
SPARSE_EMBEDDING_MODEL=<model-name>           # settings.sparse_embedding_model
EPISODIC_MEMORY_TTL_DAYS=<integer>            # settings.episodic_memory_ttl_days
EPISODIC_MEMORY_RECENT_LIMIT=<integer>        # settings.episodic_memory_recent_limit
```

## Error Handling

| Component | Failure | Behavior |
|---|---|---|
| SQL repositories (Users/Tenants/Runs/CostLog/Invitation/TrackerDBFile) | DB errors during `add`/`commit`/`query` | **No try/except anywhere in these files** — any SQLAlchemy exception (constraint violation, connection loss, etc.) propagates directly to the caller. There is no rollback-on-error logic inside the repositories themselves. |
| `UserRepository.create` / `TenantRepository.create` | N/A | Deliberately use `db.flush()` instead of `db.commit()`, leaving transaction control (commit or rollback) to the caller — this is the one place in the module showing awareness of multi-step transactional flows (e.g., create tenant + create user in one transaction) |
| `QdrantRepository.ensure_payload_indexes` | Individual index creation fails | Caught per-field, logged as a warning, loop continues — explicitly documented in the code's docstring as "a missing index degrades performance, it does not break correctness" |
| `QdrantRepository.ensure_semantic_memory_indexes` | Index creation fails | **Not caught** — propagates, unlike the sibling method above (inconsistent error-handling between these two similar methods) |
| `QdrantRepository.add_hybrid_documents` | `client.retrieve` (existence check) fails | Caught, logged via `print`, `existing_ids` defaults to empty set (fail-open toward re-embedding, not toward data loss) |
| `QdrantRepository.get_all_points` | Any exception | Caught, logged via `print`, returns `[]` |
| `QdrantRepository.search`, `create_collection`, `delete_collection`, `list_collections` | Any exception | **Not caught** — propagates directly |

Several methods across this module use `print()` for status/error messages (`qdrant.py`) alongside proper `logging` calls (`logger.info`/`logger.warning`/`logger.debug`) — the mix is inconsistent within the same file.

## Async / Background Processing

Not enough information from the provided code. All methods in this archive are synchronous (`def`, not `async def`); no threading, asyncio, or Celery task usage appears anywhere in this module.

## Observability

Only `qdrant.py` contains logging: a module-level `logger = logging.getLogger(__name__)`, used for collection-creation confirmation, per-field payload-index outcomes, and retrieval-failure warnings. It also mixes in several `print()` statements for user-facing/debug output (document ingestion counts, collection deletion confirmation). No metrics, tracing, or request-ID propagation exist anywhere in this module. The SQL repositories (`user_repository.py`, `tenant_repository.py`, `runs_repository.py`, `cost_log_repository.py`, `invitation_repository.py`, `trakcer_db_file_repositorie.py`) contain **no logging at all**.

## Security

### Implemented

- Decimal casting for cost values (`CostLogRepository.create`) avoids floating-point precision issues in stored monetary amounts.
- `TrackerDBFileRepository.is_file_processed` only treats `status == "completed"` records as "already processed," preventing a stuck/failed processing attempt from permanently blocking reprocessing.
- Qdrant payload-index docstring explicitly identifies `payload.tenant_id` indexing as "critical" for multi-tenant query performance, and the indexing method treats index-creation failure as non-fatal (availability over strict consistency for a performance-only feature).

### Not implemented / not visible in the provided code

- No tenant-isolation enforcement is built into repository base behavior — as detailed in Multi-Tenancy above, several single-record lookup methods have no tenant filter at all. Any caller that assumes every repository call is automatically tenant-safe (as the bundled README claims) would be operating on an incorrect assumption.
- No input validation/sanitization anywhere in this module — all values passed to `Model(...)` constructors and `.filter(...)` calls are used as-is; SQL-injection risk is mitigated only by SQLAlchemy's parameterized query building (standard ORM behavior), not by any explicit validation in this code.
- `QdrantRepository.search()` performs no tenant filtering — a caller that forgets to add a Qdrant-side filter clause when building `query_vector` searches could retrieve cross-tenant vector results. **This is a genuine gap in the actual code**, not a documentation artifact — the payload index exists to make such filtering fast, but the filter itself is not applied by this repository's `search()` method.
- No authentication/authorization logic anywhere in this module (as expected for a pure data-access layer, but worth stating explicitly per the documentation requirements).

## Performance

### Implemented Optimizations

- Qdrant payload indexing (`ensure_payload_indexes`, `ensure_semantic_memory_indexes`) to avoid full-collection linear scans on filtered fields, explicitly documented as critical at multi-tenant scale.
- Deduplication-before-embedding in `add_hybrid_documents` — checks existing point IDs and skips embedding generation entirely for already-ingested documents, avoiding redundant (and costly) embedding-model calls.
- `db.flush()` instead of `db.commit()` in `UserRepository.create`/`TenantRepository.create`, allowing a caller to batch multiple related inserts into one transaction/commit rather than committing per-row.
- SQL aggregation (`func.sum`/`func.avg`/`func.count`) is pushed to the database rather than pulled into Python and summed in application code, for `CostLogRepository` and `RunsRepository` stats methods.

### Potential Optimization Opportunities

- `CostLogRepository.get_by_run_id` uses `.first()` despite the model's own docstring stating a run can have multiple cost entries — if multiple entries per run are expected, this method silently returns only one of them, which could understate cost data for any caller relying on it instead of a (currently absent) `get_all_by_run_id`.
- No `joinedload`/eager-loading usage appears in any repository despite several models having relationships (`Runs.tenant`, `Runs.cost_details`, `Tenants.users`, etc.) — the bundled README's own "Common Patterns" section recommends `joinedload` to avoid N+1 queries, but no repository method in this archive actually uses it.
- `QdrantRepository.search()` takes a raw `query_vector` with no named-vector selection — given `create_collection` sets up **named** vectors (`"dense"`/`"sparse"`), it's unclear from this code alone whether `client.search(query_vector=...)` targets the `"dense"` vector implicitly or requires additional configuration; this is worth verifying against the installed `qdrant_client` version's API, not something this archive resolves.

## Cost Considerations

The only cost-bearing operation in this module is embedding generation inside `QdrantRepository.add_hybrid_documents` — both a dense-embedding call (`self.dense_model.embed_documents`) and a sparse-embedding call (`self.sparse_model.embed`) run for every batch of genuinely new documents, but are explicitly skipped when all documents in a batch already exist in Qdrant. No LLM calls occur anywhere in this module. Actual per-call dollar costs are not determinable from this code (they depend on the not-provided `EmbeddedModel` implementation and whether it calls a paid API or a local model).

## Failure Scenarios

| Failure | Expected Behavior (per code) | Impact |
|---|---|---|
| Database unavailable during a SQL repository call | No try/except in any SQL repository — exception propagates to caller | Caller (not in this archive) must handle rollback/retry; repository leaves no partial state cleanup |
| Qdrant collection doesn't exist and `create_collection` fails mid-way | `recreate_collection` call is not wrapped in try/except | Exception propagates; `ensure_payload_indexes` would not run |
| Qdrant point retrieval fails during `add_hybrid_documents`'s dedup check | Caught, `existing_ids = set()` | All documents in the batch are treated as new — leads to re-embedding/re-upserting previously-ingested documents rather than data loss or a crash |
| Individual payload index creation fails | Caught per-field in `ensure_payload_indexes`, logged, loop continues | That one field's filtering will fall back to a full collection scan; other indexes still get created |
| Semantic-memory index creation fails | **Not caught** in `ensure_semantic_memory_indexes` | Exception propagates, halting whatever setup routine called this method |
| Invitation token lookup for an expired invitation | `accept_invitation` checks `invitation.is_valid()` (delegated to the model, not provided) — if invalid, returns `None` rather than raising | Caller must check for `None` return to detect the accept failure; no exception/error message is surfaced from this repository layer |
| Tracker file `mark_completed`/`mark_failed` called for a hash with no existing record | Silent no-op, returns `None` | Caller has no explicit signal that nothing was updated unless it checks the return value |

## Testing

No test files are present in this archive. Not enough information from the provided code to describe test coverage.

## Deployment

Not enough information from the provided code — no Dockerfile, environment bootstrap, or connection-pool configuration is included in this archive. This module assumes a `Session` object and a `QdrantClient`-reachable URL are provided by the surrounding application at runtime.

## Known Limitations

### Confirmed Limitations (visible directly in the code)

- Tenant isolation is **not uniform** across this module: several lookup-by-unique-key methods (`UserRepository.find_by_email`, `find_by_id`; `RunsRepository.get_by_id`; `CostLogRepository.get_by_id`/`get_by_run_id`; `InvitationRepository.get_by_id`) perform no tenant filtering, contrary to the bundled README's blanket claim that "all queries automatically filtered by tenant_id."
- `QdrantRepository.search()` applies no tenant filter internally — tenant-safe Qdrant search filtering is the caller's responsibility, and no caller enforcing this is included in this archive.
- `CostLogRepository.get_by_run_id` returns only the first matching row (`.first()`) despite the model comment stating a run may have multiple cost log entries.
- `ensure_payload_indexes` (per-field try/except) and `ensure_semantic_memory_indexes` (no try/except) have inconsistent error-handling for structurally similar operations.
- No repository in this module wraps its write operations in try/except or performs rollback on failure — every SQL write is a raw `commit()` call with no error recovery.
- The bundled `README.md` inside this archive contains multiple code examples that do not match the actual implementation (`RunsRepository` field names, `CostLog` model shape, `Invitations`/`Invitation` class naming, and a fully fictional `QdrantRepository.search_hybrid` method with an undefined `query_text` variable and a stubbed `delete_by_tenant`). Anyone relying on that README for integration should verify against the actual `.py` files, as this documentation does.

### Potential Risks / Improvements

- Given the inconsistent tenant-filtering coverage, a review of every "lookup by unique key" method against how it's actually called elsewhere in Atlas AI (not included in this archive) would help confirm whether the missing tenant filters are intentional (justified by global-uniqueness of the lookup key) or an oversight.
- Standardizing error handling (either all repositories propagate raw exceptions, or all wrap writes with rollback-on-failure) would make failure behavior more predictable for callers.
- Adding a `get_all_by_run_id` (or similar) to `CostLogRepository` would resolve the mismatch between the model's stated one-to-many relationship and the current one-result lookup method.
- Reconciling the bundled `README.md` with the actual code (or regenerating it from source) would prevent integration mistakes for anyone reading the README instead of the code.

## Future Improvements

Not enough information from the provided code to state an actual roadmap; only the items above are supportable improvement-shaped observations.

## Summary

This module is a straightforward repository-pattern data access layer: one thin class per SQLAlchemy model handling CRUD plus a handful of tenant-scoped aggregate queries, and one more substantial class (`QdrantRepository`) managing Qdrant collections, payload indexes, and a deduplicating hybrid dense+sparse document-ingestion pipeline. Its two most significant characteristics for an engineer integrating with it are: (1) tenant isolation is applied selectively, method-by-method, rather than structurally guaranteed — several single-record lookups (including Qdrant's own `search()`) require the caller to apply tenant scoping itself; and (2) error handling is minimal and inconsistent — most SQL writes have no rollback-on-failure, and even within `qdrant.py` similar operations handle failures differently. The bundled `README.md` describes a materially different (and in places non-functional) version of this code, particularly for `RunsRepository` and `QdrantRepository.search_hybrid`, and should not be used as a substitute for reading the actual source.