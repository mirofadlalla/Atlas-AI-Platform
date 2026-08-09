# Atlas AI — Data Models Module (`app/models`)

## Overview

This module defines the SQLAlchemy ORM data model for Atlas AI's relational (PostgreSQL) persistence layer, using SQLAlchemy's modern `DeclarativeBase` style. Based strictly on the ten files provided, it defines:

- `Base` — the shared declarative base class.
- `uuid_pk()` — a reusable UUID-string primary-key column factory.
- `Tenants`, `Users` — core multi-tenant identity models.
- `Invitation` — admin-driven, token-based user invitation/signup flow.
- `TRACKER_DB_FILE` — per-tenant document ingestion tracking (dedup via file hash).
- `Runs`, `CostLog` — RAG query execution records and per-LLM-call cost/token tracking.
- `RecommendedQA` — stored tenant-scoped recommended question/answer pairs.
- `MemoryEpisode` — compressed, expiring conversation-session summaries per user/tenant.

No service layer, repository/DAO layer, Alembic migrations, or query code that reads/writes these models was included in the provided files — those are documented as **Referenced but not provided**.

## Responsibilities

- Define the relational schema (tables, columns, types, constraints, defaults) for tenants, users, invitations, ingestion tracking, RAG run/cost logging, recommended Q&A, and conversation memory episodes.
- Define ORM relationships (`relationship(...)`, `backref`, `back_populates`) that let calling code navigate between related rows in Python (e.g., `tenant.users`, `run.cost_details`) without writing explicit joins.
- Provide two small pieces of model-level business logic: `Invitation.is_expired()` and `Invitation.is_valid()`.
- Standardize primary keys as UUID strings (via `uuid_pk()`) across every table.

## Boundaries

- This module does not perform database I/O itself (no session usage, no queries) — it only defines table/column/relationship metadata. Actual reads/writes happen in service/repository code (not provided), using the `Session`/engine machinery documented separately in `app/core/db.py`.
- No Alembic migration scripts or `metadata.create_all()` invocation were provided — how/when these tables are actually created in a real database is **not enough information**.
- No Pydantic schemas (request/response models) are defined here; those live in `app.schema.*` modules referenced elsewhere (e.g. `app.schema.auth_admin.UserCreate`/`UserLogin`, seen in the separately analyzed `app/controllers/auth_controller.py`) but not provided in this module.

## Project Structure

```
app/models/
├── __init__.py            # Re-exports all model classes + Base
├── base.py                 # Base = DeclarativeBase subclass
├── uuid.py                 # uuid_pk() column factory
├── tenant.py                # Tenants
├── user.py                   # Users
├── invitation.py              # Invitation (+ is_expired/is_valid helpers)
├── TRACKER_DB_FILE.py          # TRACKER_DB_FILE (RAG ingestion tracking)
├── runs.py                      # Runs (RAG query execution log)
├── costLog.py                    # CostLog (per-LLM-call token/cost tracking)
├── recommended_qa.py               # RecommendedQA
├── memory_episode.py                # MemoryEpisode
└── README.md                         # (pre-existing documentation file, not analyzed as source code)
```

> Note: A `README.md` already existed in the provided archive. This document is freshly generated per the current request and does not treat the prior file's content as authoritative.

---

## How It Works

There is no execution flow within this module itself — it is pure schema/ORM-mapping definition. The sections below describe each file's schema and its relationships to the others.

## File-by-File Explanation

### `base.py`

**Responsibility:** Declares the shared SQLAlchemy declarative base.

**Important Components:** `Base(DeclarativeBase)` — an empty subclass; every model in this module inherits from it, so they all share the same `MetaData`/registry.

**Dependencies:** `sqlalchemy.orm.DeclarativeBase`.

**Interactions:** Imported by every other model file, and re-exported from `__init__.py`. Presumably passed to something like `Base.metadata.create_all(engine)` elsewhere (not provided).

### `uuid.py`

**Responsibility:** Provides a single reusable primary-key column definition used by every model.

**Important Components:** `uuid_pk()` — returns `Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))`. Every model calls this function to define its PK column (with varying attribute names: `id`, `run_id`, `log_id`, `episode_id`, `invitation_id`).

**Dependencies:** `sqlalchemy.Column`, `sqlalchemy.String`, `uuid` (Python stdlib).

**Interactions:** Imported by every model file except `base.py`. Note: primary keys are stored as `String` (not SQLAlchemy's native `UUID` type), and the value is generated client-side (Python `uuid.uuid4()`) at insert time via the `default=` callable, not by a database-side UUID generation function.

### `__init__.py`

**Responsibility:** Package-level aggregation — imports and re-exports `Base` and every model class so callers can do `from app.models import Users, Tenants, ...` rather than importing from individual files.

**Important Components:** `__all__` list explicitly declaring the public surface: `Base`, `Users`, `Tenants`, `TRACKER_DB_FILE`, `Invitation`, `Runs`, `CostLog`, `RecommendedQA`, `MemoryEpisode`.

**Dependencies:** All other files in this module.

**Interactions:** This is almost certainly the import path used by `app/core/db.py`, service code, and Alembic (if used) to reference the models collectively — none of those consumers were provided.

### `tenant.py`

**Responsibility:** Defines the `tenants` table — the top-level multi-tenancy boundary for the whole platform.

**Important Components:**
- `Tenants(Base)`, table `tenants`.
- Columns: `id` (UUID PK), `name` (required), `plan` (required — presumably a subscription/plan tier, though no enum/constraint limits its values), `created_at` (defaults to `datetime.utcnow` — **naive** datetime, no timezone; see Known Limitations).
- Relationships: `users` (one-to-many, `back_populates="tenant"` — matched by `Users.tenant`), `tracked_files` (one-to-many to `TRACKER_DB_FILE`, with `cascade="all, delete-orphan"` — deleting a tenant deletes its tracked-file rows).

**Dependencies:** `Base`, `uuid_pk`, `sqlalchemy.Column/DateTime/String`, `sqlalchemy.orm.relationship`, `datetime.datetime`.

**Interactions:** Referenced via `ForeignKey("tenants.id")` from `Users`, `TRACKER_DB_FILE`, `Invitation`, `Runs`, `RecommendedQA`, and `MemoryEpisode` — this is the central table every tenant-scoped table hangs off of.

### `user.py`

**Responsibility:** Defines the `users` table — per-tenant user identity, credentials, role, and an admin-approval workflow.

**Important Components:**
- `Users(Base)`, table `users`.
- Columns: `id` (UUID PK), `name` (required), `tenant_id` (FK to `tenants.id`, **nullable** — not marked `nullable=False`; see Known Limitations), `email` (required, **unique**, indexed), `created_at` (timezone-aware, defaults to `datetime.now(timezone.utc)`), `hashed_password` (required — confirms passwords are stored hashed, though the hashing algorithm itself is not in this file), `role` (defaults to `"user"`, plain string — no enum/CHECK constraint restricting values), `approval_status` (defaults to `"approved"`, documented via comment as one of `'approved'`/`'pending'`/`'rejected'`, but not enforced by a DB constraint), `approved_by` (self-referential FK to `users.id`, nullable), `approved_at` (nullable).
- Relationship: `tenant` (`back_populates="users"`, matching `Tenants.users`).

**Dependencies:** `Base`, `uuid_pk`, `sqlalchemy.Column/DateTime/String/ForeignKey`, `sqlalchemy.orm.relationship`, `datetime.datetime`/`timezone`.

**Interactions:** `email` uniqueness is enforced at the database level (`unique=True`), which is the likely source of a "duplicate email" failure referenced conceptually in the separately analyzed `AuthController.register` flow. `approved_by` self-references `Users.id`, implying an admin user approves another user's registration — the actual approval logic (who can approve, workflow transitions) is not provided.

### `invitation.py`

**Responsibility:** Defines the `invitations` table implementing an admin-driven, token-based, expiring invitation flow for onboarding new users into a tenant.

**Important Components:**
- `Invitation(Base)`, table `invitations`.
- Columns: `invitation_id` (UUID PK), `invited_email` (required, indexed), `invited_by` (FK to `users.id`, required — the inviting admin), `tenant_id` (FK to `tenants.id`, required), `token` (required, **unique**, indexed, `Text` type — the invitation link's secret), `status` (defaults to `"pending"`; documented via comment as one of `'pending'`/`'accepted'`/`'rejected'`/`'expired'`, again not DB-enforced), `user_id` (FK to `users.id`, nullable — populated once the invitation is accepted and a user account is created), `created_at` (tz-aware, defaults to now), `expires_at` (tz-aware, **defaults to `now + timedelta(days=7)`** — a fixed 7-day expiry computed at row-creation time), `accepted_at` (nullable, tz-aware, no default).
- Relationships: `invited_by_user` (to `Users`, via `foreign_keys=[invited_by]`, exposes `backref="invitations_sent"` on `Users`), `accepted_by_user` (to `Users`, via `foreign_keys=[user_id]`, `backref="invitation_acceptance"`), `tenant` (to `Tenants`, `backref="invitations"`).
- Methods:
  - `is_expired() -> bool`: returns `datetime.now(timezone.utc) > self.expires_at`.
  - `is_valid() -> bool`: returns `self.status == "pending" and not self.is_expired()`.

**Dependencies:** `Base`, `uuid_pk`, `sqlalchemy.Column/String/ForeignKey/DateTime/Text`, `sqlalchemy.orm.relationship`, `datetime.datetime/timedelta/timezone`.

**Interactions:** Two separate FKs to `Users` (`invited_by`, `user_id`) require explicit `foreign_keys=[...]` disambiguation since SQLAlchemy cannot otherwise infer which FK a given relationship refers to. `is_expired()`/`is_valid()` are pure in-Python checks against already-loaded column values — they do not query the database themselves, so they operate on whatever `expires_at`/`status` value is currently loaded on the instance (could be stale if the object was loaded long before the check).

### `TRACKER_DB_FILE.py`

**Responsibility:** Defines the `tracker_db_file` table, tracking ingestion status of documents uploaded per tenant into the RAG pipeline, explicitly documented (via docstring) as being used to prevent duplicate processing via SHA-256 hash comparison.

**Important Components:**
- `TRACKER_DB_FILE(Base)`, table `tracker_db_file` (class name is uppercase/underscore-style, unlike every other model in this module — see Known Limitations).
- Columns: `id` (UUID PK), `tenant_id` (FK to `tenants.id`, required, indexed, `String(36)` — sized to fit a standard UUID string), `file_name` (required, `String(512)`), `file_hash` (required, indexed, `String(64)` — sized for a SHA-256 hex digest, consistent with the docstring), `status` (default `"completed"`; documented via comment as `'processing'`/`'completed'`/`'failed'`, not DB-enforced — note the default is `"completed"` rather than `"processing"`, which is a somewhat unusual default for a status that should presumably start as `"processing"` when a new ingestion begins; see Known Limitations), `started_at`/`completed_at` (both nullable, no defaults), `processed_at` (defaults to `datetime.utcnow` — naive datetime).
- Relationship: `tenant` (`back_populates="tracked_files"`, matching `Tenants.tracked_files`, which has `cascade="all, delete-orphan"` on the `Tenants` side).

**Dependencies:** `Base`, `uuid_pk`, `sqlalchemy.Column/String/DateTime/ForeignKey`, `sqlalchemy.orm.relationship`, `datetime.datetime`.

**Interactions:** `file_hash` + `tenant_id` together are the implied deduplication key (per docstring), though no unique constraint spanning both columns is defined in this file — deduplication logic, if enforced, must happen in application code (not provided), not at the schema level. This table is the persistence counterpart to the ingestion flow whose entry point (`IngestController.ingest_file` → `ingest_file_task.delay(...)`) was documented in the separately analyzed `app/controllers` module.

### `runs.py`

**Responsibility:** Defines the `runs` table — one row per RAG query execution, capturing the query, answer, latency, cache status, and retrieved document IDs.

**Important Components:**
- `Runs(Base)`, table `runs`.
- Columns: `run_id` (UUID PK), `tenant_id` (FK to `tenants.id`, required, indexed), `query`/`answer` (`Text`, nullable by default since no `nullable=False`), `latency` (`Float`), `cache_hit` (`Boolean`, default `False`), `retrieved_docs_ids` (`Text` — stores document IDs, likely as a delimited string or JSON-as-text; no structured type like `ARRAY`/`JSON` is used), `created_at` (tz-aware, defaults to now).
- Relationships: `tenant` (`backref="runs"` on `Tenants` — note this uses `backref` rather than the `back_populates` pattern used elsewhere in `tenant.py`/`user.py`, an inconsistency in relationship style across the module), `cost_details` (one-to-many to `CostLog`, `back_populates="run"`, `uselist=True` — explicit, though `uselist=True` is the default for a one-to-many `relationship()` and is redundant here).

**Dependencies:** `sqlalchemy.Column/String/Float/ForeignKey/Text/Boolean/DateTime`, `sqlalchemy.orm.relationship`, `datetime.datetime/timezone`, `app.models.uuid.uuid_pk`, `Base`.

**Interactions:** This is the table the `cache_hit_total`/`vector_search_*`/`llm_query_duration_seconds` metrics (documented in the separately analyzed `app/core/monitors.py`) would presumably be persisted alongside — i.e., `Runs` looks like the durable record corresponding to a single query pipeline execution, while Prometheus metrics provide the real-time aggregate view. No code confirms this linkage directly; it is inferred from column naming (`cache_hit`, `latency`, `retrieved_docs_ids`).

### `costLog.py`

**Responsibility:** Defines the `cost_log` table — one row per LLM call within a `Run`, enabling a one-run-to-many-cost-entries model (explicitly documented in the class docstring as a deliberate design: a run may involve multiple LLM calls, e.g. a routing model plus a generation model).

**Important Components:**
- `CostLog(Base)`, table `cost_log`.
- Columns: `log_id` (UUID PK), `run_id` (FK to `runs.run_id`, **nullable**, indexed — the docstring explicitly notes "the previous UNIQUE constraint on run_id has been removed to allow this," confirming a prior schema migration/change), `input_tokens`/`output_tokens` (`Integer`), `model_name` (`String`), `cost_usd` (`Numeric(10, 6)` — fixed-precision decimal with 6 decimal places, appropriate for sub-cent LLM costs), `created_at` (tz-aware, defaults to now).
- Relationship: `run` (`back_populates="cost_details"`, matching `Runs.cost_details`).

**Dependencies:** `app.models.uuid.uuid_pk`, `sqlalchemy.Column/String/Integer/Numeric/ForeignKey/DateTime`, `sqlalchemy.orm.relationship`, `Base`, `datetime.datetime/timezone`.

**Interactions:** Directly corresponds to the `track_llm_cost(tenant_id, model_name, input_tokens, output_tokens, cost)` helper documented in the separately analyzed `app/core/monitors.py` — the parameter shapes match closely (`model_name`, `input_tokens`, `output_tokens`, `cost`), strongly suggesting that helper's Prometheus-metric recording and a `CostLog` row insertion happen together in calling code, though no such code was provided to confirm it.

### `recommended_qa.py`

**Responsibility:** Defines the `recommended_qa` table — stores tenant-scoped, precomputed/curated question-answer pairs (e.g., for a "suggested questions" UI feature).

**Important Components:**
- `RecommendedQA(Base)`, table `recommended_qa`.
- Columns: `id` (UUID PK), `tenant_id` (FK to `tenants.id`, required, indexed), `question` (`String`, required), `answer` (`Text`, required), `created_at` (defaults to `datetime.utcnow` — naive datetime, inconsistent with the tz-aware pattern used in most other newer-looking models in this module).
- No relationships are defined to/from this table in either direction (no `relationship()` call here, and no corresponding `backref`/`back_populates` on `Tenants`).

**Dependencies:** `Base`, `uuid_pk`, `sqlalchemy.Column/String/Text/DateTime/ForeignKey`, `datetime.datetime`.

**Interactions:** Isolated — no other provided model references `RecommendedQA`, and it has no ORM-navigable relationship back to `Tenants` (only a raw FK column). Any querying happens via explicit `tenant_id` filters in application code (not provided).

### `memory_episode.py`

**Responsibility:** Defines the `memory_episodes` table — persistent, compressed summaries of a user's conversation sessions (per the module docstring), presumably the durable counterpart to the "episodic memory" concepts referenced by `episodic_memory_ttl_days`/`episodic_memory_recent_limit` settings in the separately analyzed `app/core/config.py`.

**Important Components:**
- `MemoryEpisode(Base)`, table `memory_episodes`.
- Columns: `episode_id` (UUID PK), `user_id` (FK to `users.id`, required, indexed), `tenant_id` (FK to `tenants.id`, required, indexed), `session_id` (`String`, required, indexed — not a FK, so session identity is presumably managed elsewhere, e.g. Redis short-term memory per `app/core/config.py`'s `stm_ttl_seconds`/`stm_max_turns`), `summary` (`Text`, required — the compressed conversation summary itself), `raw_turns` (`Integer`, required, default `0` — presumably the count of raw conversation turns this summary was compressed from), `created_at` (tz-aware, defaults to now), `expires_at` (tz-aware, **defaults to `now + timedelta(days=90)`**).
- No relationships (`relationship()`) are defined to/from `Users` or `Tenants` — only raw FK columns.

**Dependencies:** `sqlalchemy.Column/DateTime/ForeignKey/Integer/String/Text`, `app.models.base.Base`, `app.models.uuid.uuid_pk`, `datetime.datetime/timedelta/timezone`.

**Interactions:** The 90-day `expires_at` default matches exactly the separately analyzed `app/core/config.py`'s `episodic_memory_ttl_days: int = 90` setting — however, this file **hardcodes** `timedelta(days=90)` directly rather than reading it from `settings.episodic_memory_ttl_days`, meaning the two values would drift out of sync if the config setting were ever changed without also updating this model (see Known Limitations). No code that actually deletes/prunes expired episodes was provided — `expires_at` is a stored value only; enforcement (a scheduled job, a query filter, or a DB-level TTL) is **not enough information from the provided code**.

---

## Agent / RAG / Memory / Tools

**Partially implemented (schema only).** This module defines the persistence schema for RAG execution (`Runs`, `CostLog`), ingestion tracking (`TRACKER_DB_FILE`), and conversation memory (`MemoryEpisode`), but contains no retrieval, embedding, agent-graph, or memory read/write logic — those live in service code not provided.

## Caching

**Referenced only.** `Runs.cache_hit` (Boolean) confirms that cache-hit/miss outcomes are recorded per query run, consistent with the `CACHE_HIT_COUNTER`/`cache_hits_total` Prometheus metrics documented separately in `app/core`. No cache implementation exists in this module.

## Multi-Tenancy

**Schema-level isolation only — not enforced by this module at query time.**

- Every tenant-scoped table (`Users`, `TRACKER_DB_FILE`, `Invitation`, `Runs`, `RecommendedQA`, `MemoryEpisode`) carries a `tenant_id` foreign key to `Tenants.id`, and all but `Users.tenant_id` mark it `nullable=False`.
- **`Users.tenant_id` is nullable** (no `nullable=False`), meaning the schema as defined permits a user with no tenant association — this is an exception to the otherwise-consistent tenant-scoping pattern and worth confirming is intentional (e.g. for a platform-super-admin role) or an oversight.
- No row-level security, SQLAlchemy query-filtering hooks, or session-scoped tenant context are defined in this module — enforcing that queries are always filtered by `tenant_id` is entirely the responsibility of application/service code (not provided). The schema makes tenant isolation *possible* but does not itself *guarantee* it.
- `Tenants.tracked_files` uses `cascade="all, delete-orphan"`, meaning deleting a `Tenants` row will cascade-delete its `TRACKER_DB_FILE` rows at the ORM level (only when using the ORM's cascade machinery, not via raw SQL `DELETE`). No equivalent cascade is defined for `Users`, `Invitation`, `Runs`, `RecommendedQA`, or `MemoryEpisode` relative to `Tenants` — deleting a tenant would leave those rows orphaned (or fail on FK constraint, depending on DB-level `ON DELETE` behavior, which is not specified in any of these `ForeignKey(...)` calls and therefore defaults to the database's default, typically `NO ACTION`/`RESTRICT`).

## Data Flow

```text
Tenants (root)
   ├─→ Users (tenant_id FK)
   │      ├─→ Invitation.invited_by_user (FK: invited_by)
   │      └─→ Invitation.accepted_by_user (FK: user_id, nullable)
   ├─→ TRACKER_DB_FILE (tenant_id FK, cascade delete-orphan)
   ├─→ Invitation (tenant_id FK)
   ├─→ Runs (tenant_id FK)
   │      └─→ CostLog (run_id FK, one run → many cost entries)
   ├─→ RecommendedQA (tenant_id FK, no ORM relationship)
   └─→ MemoryEpisode (tenant_id FK + user_id FK, no ORM relationship)
```

## External Dependencies

| Dependency | Purpose | Where Used | Required? |
|---|---|---|---|
| SQLAlchemy (ORM, `DeclarativeBase`, `Column`, `relationship`) | Defines all table schemas and object-relational mappings | Every file | Required |
| PostgreSQL (implied) | Target relational database; `Numeric(10,6)` and `String(36)`/`String(64)`/`String(512)` sizing choices are consistent with a PostgreSQL/SQL-standard backend, matching the `postgresql+psycopg2` driver seen in the separately analyzed `app/core/db.py` | Implied target for all tables | Not enough information within this module alone — confirmed by the separately analyzed `app/core/db.py` |
| Python stdlib `uuid` | Client-side UUID generation for primary keys | `uuid.py` | Required |
| Python stdlib `datetime` | Timestamp defaults (`utcnow`, `now(timezone.utc)`, `timedelta`) | Nearly every model file | Required |

## Configuration

**Not enough information from the provided code.** No environment variables or settings objects are referenced in this module. Table names, column sizes, and default values (e.g., the 7-day invitation expiry, the 90-day memory-episode expiry) are all hardcoded in the model definitions rather than read from configuration — notably, the 90-day `MemoryEpisode.expires_at` default duplicates (rather than reads from) the `episodic_memory_ttl_days` setting documented in the separately analyzed `app/core/config.py`.

## API Reference

**Not applicable.** This module contains no HTTP-facing code.

## Error Handling

No explicit error handling exists in this module — all validation is expressed declaratively via SQLAlchemy column constraints (`nullable=False`, `unique=True`) and would surface as database-level integrity errors (e.g., `IntegrityError` on a duplicate `Users.email`, a duplicate `Invitation.token`, or a `NOT NULL` violation) when a session is flushed/committed by calling code. No model-level validation methods exist except `Invitation.is_expired()`/`is_valid()`, which are pure boolean checks and never raise.

## Async / Background Processing

**Not applicable directly**, though `TRACKER_DB_FILE.status` (`'processing'`/`'completed'`/`'failed'`) is clearly designed to track the lifecycle of an asynchronous background task — presumably the `ingest_file_task` Celery task documented in the separately analyzed `app/controllers/ingest_rag_controller.py`. No code that transitions `status` between these values was provided.

## Observability

**Schema supports it; no instrumentation here.** `Runs` and `CostLog` together form a durable, queryable observability record (query text, answer, latency, cache-hit flag, retrieved doc IDs, per-call token counts and cost) that closely parallels the Prometheus metrics defined in the separately analyzed `app/core/monitors.py`/`metrics.py`. This module defines the storage shape only; nothing here writes to Prometheus or vice versa.

## Security

- **Password storage:** `Users.hashed_password` confirms passwords are not stored in plaintext, but the hashing algorithm/library is not defined in this file.
- **Invitation tokens:** `Invitation.token` is `unique=True` and indexed, suitable for token-based lookup; no information on token generation/entropy is present in this module (that logic lives in service code, not provided).
- **Tenant isolation:** As discussed above, isolation is schema-supported but not schema-enforced — enforcement is delegated entirely to application code.
- **Self-referential approval:** `Users.approved_by` references `users.id` with no constraint preventing a user from referencing themselves (`approved_by == id`), nor any constraint tying `approved_by`'s role to `"admin"` — such a rule, if it exists, is enforced in application logic not provided here.
- **No soft-delete/audit trail:** none of these models include a `deleted_at`/`is_deleted` column or an audit-log pattern; deletions (where cascade is defined) are hard deletes at the schema level.

## Performance

### Implemented Optimizations
- Indexes are defined on frequently-filtered/looked-up columns: `Users.email`, `TRACKER_DB_FILE.tenant_id`/`file_hash`, `Invitation.invited_email`/`token`, `Runs.tenant_id`, `CostLog.run_id`, `RecommendedQA.tenant_id`, `MemoryEpisode.user_id`/`tenant_id`/`session_id`.
- `CostLog.run_id`'s unique constraint was explicitly removed (per its docstring) to support the one-to-many relationship needed for multi-call runs, avoiding an awkward workaround (e.g., a separate junction table) for what is fundamentally a one-to-many relationship.

### Potential Optimization Opportunities
- `RecommendedQA` and `MemoryEpisode` have `tenant_id` (and `user_id`, for `MemoryEpisode`) indexed individually, but no composite index (e.g., `(tenant_id, user_id)`, or `(tenant_id, session_id)`) is defined — depending on query patterns (not provided), a composite index could improve lookup performance for these tenant+user/session-scoped queries.
- `Runs.retrieved_docs_ids` is stored as `Text` rather than a structured/indexable type (e.g., PostgreSQL `ARRAY(String)` or `JSONB`), which would make it harder to query "which runs retrieved document X" efficiently without a separate join table.

## Cost Considerations

`CostLog` is the schema that persists per-LLM-call cost (`cost_usd`, `input_tokens`, `output_tokens`, `model_name`), directly enabling the cost-tracking metrics documented in `app/core/monitors.py`'s `track_llm_cost`. No cost computation happens in this module — `cost_usd` is simply stored as provided by calling code.

## Sequence Diagrams

**Not applicable** — this module contains no control flow between components; it is a static schema definition.

## End-to-End Example

A plausible (inferred, not directly observed) lifecycle spanning multiple provided models:

1. A `Tenants` row is created (e.g., during org onboarding — not provided).
2. An admin `Users` row (with `role="admin"` and `approval_status="approved"`) sends an `Invitation` (`invited_by` = admin's `id`, `tenant_id` = the tenant, `expires_at` = now + 7 days).
3. The invited person accepts, creating a new `Users` row and setting `Invitation.user_id`/`status="accepted"`/`accepted_at` (logic not provided; `is_valid()` would presumably gate this).
4. A document is uploaded and ingested — a `TRACKER_DB_FILE` row is created with `status="processing"` (though the column's own default is `"completed"`, implying calling code explicitly sets `"processing"` at creation time), then updated to `"completed"`/`"failed"` once the Celery task (not provided) finishes.
5. A user issues a RAG query — a `Runs` row is created capturing `query`, `answer`, `latency`, `cache_hit`, `retrieved_docs_ids`; one or more `CostLog` rows are created (one per LLM call within that run) linked via `run_id`.
6. Over a conversation session, turns accumulate; eventually a `MemoryEpisode` row is created summarizing that session, with a 90-day expiry.
7. Separately, curated `RecommendedQA` rows may exist per tenant for a "suggested questions" feature, unrelated to any specific `Runs` row.

## Design Decisions

- The implementation suggests `uuid_pk()` was factored out specifically to guarantee every table in the platform uses the same PK style (client-generated UUID string), likely to keep IDs stable/predictable across services (e.g., a `Runs.run_id` generated in application code before insertion, for use in logs/traces) rather than relying on database-assigned auto-increment integers.
- The implementation suggests `CostLog` was deliberately split from `Runs` (rather than storing cost fields directly on `Runs`) specifically because a single run can involve multiple LLM calls — this is stated directly in the `CostLog` docstring, including the note that a prior unique constraint was removed to support it, evidencing an actual schema migration that occurred.
- The implementation suggests `TRACKER_DB_FILE` exists specifically to make ingestion idempotent (avoid reprocessing an already-ingested file) via `file_hash`, per its docstring — though the *enforcement* of that idempotency (checking `file_hash` before enqueueing) is not in this module.
- The implementation suggests `Invitation.expires_at`'s default (7 days) and `MemoryEpisode.expires_at`'s default (90 days) reflect different data-retention/validity philosophies for different kinds of ephemeral state — an invitation link should be short-lived for security, while a conversation-memory summary is kept much longer for continuity of user experience.
- The implementation suggests the inconsistent use of `back_populates` (in `tenant.py`/`user.py`/`costLog.py`) versus `backref` (in `runs.py`, `invitation.py`) reflects code written at different times or by different contributors rather than a single deliberate architectural choice — both achieve bidirectional relationships, but mixing the two styles within one module is a stylistic inconsistency rather than a documented decision.

## Failure Scenarios

| Failure | Expected Behavior | Impact |
|---|---|---|
| Duplicate `Users.email` insert | Database raises an `IntegrityError` (unique constraint violation) | Registration fails at the DB layer; must be caught by calling code (the separately analyzed `AuthController.register` does not catch this itself) |
| Duplicate `Invitation.token` insert | Database raises an `IntegrityError` | Whatever generates tokens (not provided) must ensure sufficient uniqueness/entropy to make this practically rare |
| Insert into a tenant-scoped table with an invalid/nonexistent `tenant_id` | Database raises a foreign-key constraint violation | Prevents orphaned tenant-scoped rows at the DB level, for every table except where the FK is nullable (`Users.tenant_id`, `CostLog.run_id`) |
| Deleting a `Tenants` row with existing `Users`/`Runs`/`Invitation`/`RecommendedQA`/`MemoryEpisode` rows | Not enough information — no `ON DELETE` behavior is specified on those FKs (only `TRACKER_DB_FILE` has an explicit ORM-level cascade via `Tenants.tracked_files`) | Likely blocked by the database's default FK behavior (commonly `RESTRICT`/`NO ACTION` in PostgreSQL unless otherwise configured), but this is inferred from SQL defaults, not shown in code |
| `MemoryEpisode`/`Invitation` rows past their `expires_at` | Not enough information — no cleanup job, query filter, or deletion logic exists in this module | Expired rows will simply remain in the database indefinitely unless pruned by code not provided |

## Testing

No tests were provided in the analyzed code.

## Deployment

No deployment or migration configuration (Alembic, `create_all()` call, seed data) was provided in the analyzed code. The presence of `Base` and consistent column typing implies these models are intended to be registered with an Alembic migration environment or a `Base.metadata.create_all(engine)` call, but neither was included.

## Known Limitations

### Confirmed Limitations
- `Users.tenant_id` is the only tenant-scoping FK across the module that is **not** `nullable=False`, making it schema-legal for a user to have no tenant — inconsistent with every other tenant-scoped model in this module (`TRACKER_DB_FILE`, `Invitation`, `Runs`, `RecommendedQA`, `MemoryEpisode` all mark `tenant_id` as `nullable=False`).
- `TRACKER_DB_FILE.status` defaults to `"completed"` rather than `"processing"`, despite the class docstring describing the lifecycle as `'processing' -> 'completed' | 'failed'` — a row created without explicitly setting `status` would be marked complete by default, which is inconsistent with the documented lifecycle.
- `TRACKER_DB_FILE` is the only model class in the entire module named in uppercase/underscore style (`TRACKER_DB_FILE`) rather than the `PascalCase` used by every other model (`Users`, `Tenants`, `Invitation`, `Runs`, `CostLog`, `RecommendedQA`, `MemoryEpisode`) — a naming inconsistency, though functionally harmless.
- `created_at` timestamp handling is inconsistent across the module: `Tenants`, `TRACKER_DB_FILE`, and `RecommendedQA` use naive `datetime.utcnow`, while `Users`, `Invitation`, `Runs`, `CostLog`, and `MemoryEpisode` use timezone-aware `datetime.now(timezone.utc)` with `DateTime(timezone=True)` columns. Comparing or sorting timestamps across these tables (e.g., joining `Tenants.created_at` against `Users.created_at`) could produce naive-vs-aware comparison errors in application code.
- `MemoryEpisode.expires_at`'s `timedelta(days=90)` default is hardcoded rather than sourced from the separately analyzed `app/core/config.py`'s `episodic_memory_ttl_days` setting — the two are currently numerically identical (90) but not structurally linked, so a future change to the config setting would silently stop affecting this model's default.
- Neither `RecommendedQA` nor `MemoryEpisode` define an ORM `relationship()` back to `Tenants`/`Users`, unlike every other tenant-scoped model — this is a structural inconsistency (they use raw FK columns only), meaning `tenant.recommended_qa` or `user.memory_episodes`-style navigation is not available and callers must query these tables explicitly by `tenant_id`/`user_id`.

### Potential Risks / Improvements
- Consider a composite unique constraint on `TRACKER_DB_FILE(tenant_id, file_hash)` if per-tenant dedup is the intended guarantee — currently, only `file_hash` is individually indexed, and nothing at the schema level prevents the same hash from being inserted twice for the same tenant.
- Consider defining explicit `ondelete=` behavior on foreign keys (e.g., `ForeignKey("tenants.id", ondelete="CASCADE")`) for tables where cascading tenant deletion is desired, rather than relying solely on the ORM-level `cascade` (which only applies to `TRACKER_DB_FILE` today and only takes effect through the ORM, not raw SQL).
- Consider adding DB-level `CHECK` constraints (or an `Enum` type) for the string-based status fields (`Users.role`, `Users.approval_status`, `TRACKER_DB_FILE.status`, `Invitation.status`) which are currently only constrained by code comments, not the schema itself.
- Consider standardizing on timezone-aware timestamps across all models, since the mixed naive/aware pattern is a common source of subtle bugs when comparing dates across tables.

## Future Improvements

Not stated in the provided code — no roadmap, TODO comments, or planning documents were included, aside from the `CostLog` docstring's mention of a prior constraint having been removed (a completed change, not a future one).

## Summary

This module defines a coherent, tenant-rooted relational schema for Atlas AI: `Tenants` and `Users` anchor identity and multi-tenancy; `Invitation` implements a token-based, expiring admin-invite signup flow; `TRACKER_DB_FILE` tracks RAG document ingestion status for deduplication; `Runs` and `CostLog` together persist a durable record of each RAG query execution and its per-LLM-call token/cost breakdown; `RecommendedQA` stores tenant-scoped curated Q&A pairs; and `MemoryEpisode` stores compressed, 90-day-expiring conversation summaries per user/tenant. The schema supports — but does not itself enforce — tenant isolation, and shows several concrete inconsistencies (nullable `Users.tenant_id`, mixed naive/aware timestamps, mixed `relationship()` styles, an unusual default on `TRACKER_DB_FILE.status`, and a hardcoded duplicate of the memory-episode TTL) that are worth reconciling with the service/config code that was not included in this analysis.