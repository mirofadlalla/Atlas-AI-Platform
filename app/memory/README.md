# Atlas AI — Memory Module

## Overview

This module (`app/memory/`) implements Atlas AI's multi-layer memory system. It provides four distinct memory stores — short-term (Redis, per-session), semantic (Qdrant, long-term durable facts), episodic (PostgreSQL via a repository, compressed cross-session summaries), and working memory (in-request, token-budgeted prompt assembly) — plus supporting utilities for token counting, LLM-based session summarization, and LLM-based fact extraction.

**Provided code:** `__init__.py` (14 lines), `short_term_memory.py` (141 lines), `semantic_memory.py` (223 lines), `episodic_memory.py` (64 lines), `working_memory.py` (65 lines), `token_counter.py` (34 lines), `summarizer.py` (31 lines), `memory_extractor.py` (56 lines). No `README.md` was included in this zip.

**Not provided / Referenced but not provided:** `app.core.config.settings` (all `stm_*`, `qdrant_url`, `semantic_memory_*` settings), `app.core.db.get_db_session`, `app.repositories.episode_repository.EpisodeRepository` (and its underlying ORM/table schema), `app.agent.utils.llm.call_agent_llm`, `app.agent.utils.parsing.extract_first_json_block`, `app.design_pattern.embedded_model.EmbeddedModel` (reviewed in a separate module previously), and any caller code (agent graph, API routes) that reads from or writes to these memory stores.

---

## Responsibilities

* Persist and retrieve bounded, per-session conversation history (`ShortTermMemory`).
* Persist and semantically retrieve durable, tenant/user-scoped facts, preferences, and tool hints (`SemanticMemory`).
* Persist and retrieve compressed cross-session conversation summaries (`EpisodicMemory`).
* Assemble a token-budgeted prompt context from multiple prioritized sources without persisting anything (`WorkingMemory`).
* Count/estimate and truncate text by token count (`TokenCounter`).
* Use an LLM to summarize a session's turns into a durable episode (`SessionSummarizer`).
* Use an LLM to extract durable facts from a completed Q&A turn and store them via `SemanticMemory` (`MemoryExtractor`).

## Boundaries

* None of these classes perform retrieval-augmented generation, prompt construction beyond `WorkingMemory.assemble()`, or agent orchestration — they are storage/retrieval/assembly primitives consumed by something else (not provided).
* `SessionSummarizer` and `MemoryExtractor` depend on an external LLM call function (`call_agent_llm`) that is not defined in this module — their behavior is bounded by what they send to and parse from that function's return value.
* Cross-tenant/cross-user isolation is enforced only where explicitly coded (see Multi-Tenancy section) — this module does not have a separate, centralized isolation-enforcement layer; each store implements its own filtering.

---

## Project Structure

```
memory/
├── __init__.py             # Re-exports ConversationTurn, ShortTermMemory,
│                            # SemanticMemory, EpisodicMemory, WorkingMemory
├── short_term_memory.py     # Redis-backed per-session conversation turns
├── semantic_memory.py       # Qdrant-backed durable fact/preference/tool_hint store
├── episodic_memory.py       # DB-backed cross-session episode summaries
├── working_memory.py        # In-request, priority + token-budget context assembly
├── token_counter.py         # tiktoken-based (or approximate) token counting/truncation
├── summarizer.py            # LLM-based session-turn summarization
└── memory_extractor.py      # LLM-based durable fact extraction + storage
```

Note: `__init__.py` exports `WorkingMemory` and `SemanticMemory`/`EpisodicMemory`/`ShortTermMemory`, but does **not** export `TokenCounter`, `SessionSummarizer`, or `MemoryExtractor` — those must be imported from their submodules directly.

---

## Memory System

Atlas AI's memory is split into four distinct layers, matching the module's docstrings and class responsibilities:

| Layer | Class | Storage Backend | Scope | Lifetime |
|---|---|---|---|---|
| Short-term | `ShortTermMemory` | Redis | tenant + user + session | Bounded by `ttl_seconds` and `max_turns` |
| Semantic (long-term) | `SemanticMemory` | Qdrant (vector DB) | tenant + user | Durable until explicitly forgotten/pruned |
| Episodic | `EpisodicMemory` | Relational DB (via `EpisodeRepository`) | tenant + user + session | Durable until explicitly cleared |
| Working | `WorkingMemory` | None — in-memory, per call | Whatever is passed to `.add()` for one `.assemble()` call | Single request only; not persisted |

### Short-Term Memory (`short_term_memory.py`)

**Storage backend:** Redis, accessed via a fresh `redis.from_url(settings.REDIS_URL, decode_responses=True)` client created per operation (no client reuse/pooling visible in this file).

**Key schema:** `atlas:stm:{tenant_id}:{user_id}:{session_id}` (via the static `key()` method).

**Write path (`save`):**
1. No-op if `session_id` is falsy.
2. Normalizes the input `turn` (accepts either a `ConversationTurn` dataclass or a plain dict) into a `record` dict; fills in `timestamp` with the current UTC ISO time if missing.
3. Rejects the turn (logs a warning, returns) if `role` isn't `"user"` or `"assistant"`, or `content` is empty/whitespace.
4. Performs an atomic **read-modify-write via a Redis `WATCH`/`MULTI` pipeline**: reads current history, appends the new record, trims to the last `max_turns` entries, and writes back with `SETEX` (refreshing the TTL on every write). A `WatchError` (optimistic-lock conflict from a concurrent writer) is retried in a loop; any other exception is re-raised to the outer handler.
5. Any exception at the outer level is caught, logged as a warning, and swallowed — writes are "fail-open" per the module's docstring ("Redis failures are deliberately non-fatal").

**Read path (`load`):** Returns `[]` immediately if `session_id` is falsy. Otherwise fetches the Redis value, JSON-decodes it, and filters to only well-formed entries (`dict` with truthy `role` and `content`). Any exception (connection failure, malformed JSON, etc.) is caught, logged, and results in an empty list rather than a raised error.

**TTL:** `ttl_seconds` (constructor param or `settings.stm_ttl_seconds`) is refreshed on every `save` via `SETEX`.

**Bounding:** `max_turns` (constructor param or `settings.stm_max_turns`) caps stored history length via `history[-self.max_turns:]` on every write.

**Deletion:** `clear()` deletes a single session's key. `clear_all()` uses `SCAN` with pattern `atlas:stm:{tenant_id}:{user_id}:*` to find and delete **every session key for one user**, explicitly scoped so other users' keys are untouched (per the docstring and the pattern's structure).

**Failure behavior:** Every public method (`load`, `save`, `clear`, `clear_all`) wraps its Redis interaction in `try/except Exception`, logs a warning, and returns a safe default (`[]`, `None`, or `0`) rather than propagating the exception — consistent with the class docstring's explicit design intent that "memory must never prevent a user from receiving an answer."

### Semantic Memory (`semantic_memory.py`)

**Storage backend:** Qdrant, via `QdrantClient(url=settings.qdrant_url)` (or an injected client). Embeddings are produced by an injected or default `EmbeddedModel()` instance (from the separately-reviewed `design_pattern` module).

**Collection setup (`_ensure_collection`):** Lazily creates the collection (name from `settings.semantic_memory_collection` or constructor override) with a single named dense vector (`"dense"`, cosine distance, size determined by the actual embedding vector's length at first write). Also attempts to create payload indexes on `tenant_id`, `user_id`, `memory_type` (all `KEYWORD`), and `importance` (`FLOAT`) — index-creation failures are caught individually and logged at `debug` level, not treated as fatal (e.g., the index may already exist).

**Payload schema (per point):**
```json
{
  "content": "<fact text, truncated to 4000 chars>",
  "tenant_id": "<str(tenant_id)>",
  "user_id": "<str(user_id)>",
  "memory_type": "fact | preference | tool_hint",
  "importance": "<float, clamped to [0.0, 1.0]>",
  "created_at": "<UTC ISO timestamp>"
}
```

**Write path (`store`):**
1. Strips the input fact; returns `None` if empty.
2. Validates `memory_type` against `_ALLOWED_TYPES = {"fact", "preference", "tool_hint"}`, **raising `ValueError`** (not caught internally) if invalid — this is the one write-path error that is not fail-open.
3. Embeds the fact via `embedding_model.embed_documents([fact])[0]`.
4. Ensures the collection/indexes exist (sized to the actual embedding dimension).
5. Upserts a single point with a fresh UUID id, the dense vector, and the payload above; `importance` is clamped to `[0.0, 1.0]` before storage.
6. Logs an info-level line with id, tenant, user, type, and importance. Returns the new memory's id.

**Read path (`recall`):**
1. Returns `[]` immediately for an empty/whitespace query.
2. Returns `[]` if the collection doesn't exist yet (no memories stored for any tenant).
3. Queries Qdrant with `query_points`, embedding the query via `embedding_model.embed_query(query)`, using the `"dense"` named vector, filtered by an **AND filter requiring both `tenant_id` and `user_id` to match exactly** (`models.Filter(must=[...])`), limited to `top_k` (constructor override or `settings.semantic_memory_top_k`).
4. Re-ranks the raw Qdrant results client-side: `score * (0.5 + 0.5 * importance)` — i.e., relevance score is blended with stored importance, giving importance up to a 1.5x multiplier over pure similarity, before sorting descending.
5. Filters out points with no payload/content.
6. Any exception (Qdrant unreachable, embedding failure, etc.) is caught, logged as a warning, and results in an empty list — fail-open, same pattern as short-term memory.

**Delete paths:**
* `forget(memory_id, user_id, tenant_id)` — retrieves the point first, verifies its stored `tenant_id`/`user_id` match the caller's before deleting; returns `False` (not an error) if the point doesn't exist or ownership doesn't match. This is the module's explicit ownership-check mechanism, preventing one user from deleting another's memory even if they somehow obtain its id.
* `clear_user(user_id, tenant_id)` — bulk-deletes all points matching both `tenant_id` and `user_id` via a `FilterSelector`.
* `prune_low_importance(threshold)` — bulk-deletes points where `importance < threshold`, **globally, across all tenants and users** (no tenant/user filter in this specific method) — this is the method routed to the nightly Celery Beat task in the previously-reviewed `celery` module (`prune_low_importance_semantic_memories`).

All delete/clear operations follow the same fail-open pattern: exceptions are caught, logged, and the method returns `False`/`0` rather than raising.

### Episodic Memory (`episodic_memory.py`)

**Storage backend:** A relational database, accessed exclusively through `app.repositories.episode_repository.EpisodeRepository`, itself wrapped by `app.core.db.get_db_session()` as a context manager. Neither the repository's internals nor the DB schema are provided — this class is a thin, fail-open wrapper around that repository.

**Write path (`save_episode`):** No-op (`None`) if `session_id` is falsy or `summary` is empty/whitespace. Otherwise opens a DB session, calls `EpisodeRepository(db).save_episode(session_id, summary, str(user_id), str(tenant_id), raw_turns)`, logs an info line with the resulting `episode.episode_id`, and returns that id. Any exception is caught, logged as a warning, and `None` is returned.

**Read path (`get_recent`):** Delegates to `EpisodeRepository(db).get_recent(str(user_id), str(tenant_id), limit, exclude_session_id)`, returning just the `.summary` strings. `exclude_session_id` suggests episodes are excludable by session — presumably to avoid re-injecting the summary of the *current* session as if it were a past one, though the repository logic itself is not provided to confirm this. Any exception is caught and results in `[]`.

**Delete path (`clear_user`):** Delegates to `EpisodeRepository(db).clear_user(str(user_id), str(tenant_id))`, returning the count deleted, or `0` on any exception.

All tenant/user scoping for episodic memory is delegated entirely to `EpisodeRepository` — this class itself performs no filtering logic of its own beyond passing `str(tenant_id)`/`str(user_id)` through.

### Working Memory (`working_memory.py`)

**Not a persistence layer** — explicitly "Fits useful context into a fixed token budget without storing it" (module docstring). Scoped to a single call chain, not saved anywhere.

**Usage pattern:** `WorkingMemory(max_tokens).add(source, content, priority, max_tokens=None).add(...)...assemble()`.

**`add`:** Silently skips items with empty/whitespace `content`. Each accepted item becomes a `ContextItem(source, content.strip(), priority, max_tokens)`. Returns `self`, allowing chained `.add()` calls.

**`assemble`:**
1. Sorts stored items by `priority` **ascending** (i.e., lower `priority` values are placed first / win the budget first — the code does not document which numeric direction means "more important," but ascending sort order combined with sequential budget consumption means lower-numbered priorities are served first).
2. For each item, in that order: builds a `=== SOURCE ===\n` header, checks whether the header alone would exceed remaining budget (skips the item if so), computes the token allowance for content as `remaining - header_tokens`, further capped by the item's own `max_tokens` if set, truncates content to that allowance via `TokenCounter.truncate`, and skips the item entirely if truncation left no content or the rendered block still exceeds the remaining budget.
3. Accepted items are joined with `"\n\n"`; `self.context_sources` is populated with the source names actually included (useful for the caller to know what was/wasn't included); `self.tokens_used` records the total consumed.

This gives priority-ordered, hard-token-budgeted context assembly with graceful degradation (lower-priority items are dropped first when the budget is tight) rather than proportional truncation across all sources.

### Token Counter (`token_counter.py`)

Wraps `tiktoken.encoding_for_model(model)` (default model string: `"gpt-4o-mini"`) if available; falls back to a rough character-based approximation (`(len(text) + 3) // 4`, minimum 1) if `tiktoken` import or encoding-lookup fails for any reason (caught with a bare `except Exception`).

`truncate(text, max_tokens, suffix="\n...[truncated]")`: returns `""` if `max_tokens <= 0`; returns the original text unchanged if it already fits; otherwise truncates at the token level (using the real encoding if available, or a `4 chars ≈ 1 token` heuristic otherwise) and appends the suffix, reserving budget for the suffix's own token cost when a real encoding is available.

### Session Summarizer (`summarizer.py`)

Not part of `__init__.py`'s exports. `SessionSummarizer.summarize(turns, tenant_id)`:
1. Joins turns into a `Role: content` transcript (role title-cased, defaulting to `"user"` if missing).
2. Returns `""` immediately if the resulting transcript is empty/whitespace.
3. Builds a fixed prompt instructing the LLM to produce a 2–3 sentence factual summary covering "user goals, conclusions, and unresolved follow-ups," explicitly excluding "chain-of-thought, credentials, or unsupported claims" — this is a concrete, in-code prompt-level safety instruction, not just a description.
4. Truncates the raw conversation text embedded in the prompt to the first 12,000 characters (`conversation[:12000]`) — a hard cap independent of `TokenCounter`, i.e. character-based, not token-based.
5. Calls `call_agent_llm(prompt, tier="generation", tenant_id=tenant_id)` (imported lazily inside the method — the module comment explains this delayed import "keeps API startup independent from agent graph setup") and returns the `.strip()`ped `"content"` field of its response.
6. Any exception (including from the LLM call itself) is caught, logged as a warning, and `""` is returned — fail-open, consistent with the rest of the module.

### Memory Extractor (`memory_extractor.py`)

Not part of `__init__.py`'s exports. `MemoryExtractor.extract_and_store(question, answer, user_id, tenant_id)`:
1. Returns `[]` immediately if either `question` or `answer` is empty/whitespace.
2. Builds a fixed prompt instructing the LLM to extract only "user preferences, stable facts, or reusable database/tool hints," explicitly forbidding "secrets, credentials, transient requests, unsupported claims, or chain-of-thought," and requiring a strict JSON response shape: `{"memories":[{"content":"...","memory_type":"fact|preference|tool_hint","importance":0.0}]}` (empty list allowed).
3. Calls `call_agent_llm(...)`, then parses the first JSON block out of the raw response text via `extract_first_json_block` (imported from `app.agent.utils.parsing`, not provided) and `json.loads`. Any exception here (LLM failure, malformed JSON, missing `"memories"` key handled via `.get("memories", [])`) is caught, logged, and results in an empty list.
4. Instantiates a **new, unshared `SemanticMemory()`** (not injected — a fresh default instance is created inside this method).
5. Iterates at most the **first 5** extracted items (`extracted[:5]`), skips any that aren't dicts, and calls `store.store(...)` per item, casting `content`/`memory_type` to `str` and `importance` to `float` (defaulting to `"fact"`/`0.5` if absent). `TypeError`/`ValueError` from an individual item (e.g. `store`'s `ValueError` on an invalid `memory_type`, or a non-numeric `importance`) are caught **per item** and logged, without aborting the remaining items in the batch — this differs from the broader `try/except Exception` pattern used elsewhere in the module; here the exception types are narrowed and scoped to a single loop iteration.
6. Returns the list of successfully stored memory ids.

---

## Multi-Tenant Data Isolation

This module enforces tenant/user isolation independently in each store, using different mechanisms:

```text
Caller supplies tenant_id + user_id (+ session_id where applicable)
        │
        ▼
┌─────────────────────┬─────────────────────┬─────────────────────┐
│ ShortTermMemory       │ SemanticMemory        │ EpisodicMemory        │
│ Key namespacing:      │ Qdrant payload filter: │ Delegated entirely to │
│ atlas:stm:{tenant}:   │ Filter(must=[tenant_id │ EpisodeRepository,    │
│ {user}:{session}      │  == X, user_id == Y])  │ str(tenant_id)/       │
│                       │ on every recall/clear   │ str(user_id) passed   │
│ clear_all() scans     │ forget() additionally   │ through — actual      │
│ only atlas:stm:       │ verifies point owner-   │ filtering logic is    │
│ {tenant}:{user}:*     │ ship before deleting     │ Not provided          │
└─────────────────────┴─────────────────────┴─────────────────────┘
```

* **Short-term memory** isolates by constructing tenant/user/session into the Redis key itself — there is no cross-key query capability in this file, so isolation is structural (a caller can only read/write the key it constructs).
* **Semantic memory** isolates via an explicit Qdrant `Filter(must=[...])` requiring both `tenant_id` and `user_id` to match on every `recall`, and via an explicit ownership check (`payload.get("tenant_id") != ... or payload.get("user_id") != ...`) before allowing `forget()` to delete a specific point by id.
* One exception: `prune_low_importance` operates **without** any tenant/user filter — it deletes globally by `importance` threshold alone, which is a deliberate global maintenance operation (consistent with its use as a scheduled/Beat task), not a per-tenant query.
* **Episodic memory** isolation is delegated to `EpisodeRepository`, which is not included in this zip — this document cannot confirm how (or whether) that repository enforces tenant/user filtering at the query level; it can only confirm that `str(tenant_id)`/`str(user_id)` are passed to it on every call in this file.

`Not enough information from the provided code` regarding how `tenant_id`/`user_id`/`session_id` are originally derived or authenticated before reaching these classes — that responsibility sits with calling code not included in this zip.

---

## External Dependencies

| Dependency | Purpose | Where Used | Required? |
|---|---|---|---|
| `redis` | Short-term memory storage | `short_term_memory.py` (imported lazily inside `_client()`) | Yes |
| `qdrant_client` (`QdrantClient`, `models`) | Semantic memory vector storage, filtering, indexing | `semantic_memory.py` | Yes |
| `app.design_pattern.embedded_model.EmbeddedModel` | Produces embeddings for semantic memory | `semantic_memory.py` (default, overridable) | Yes, unless a custom `embedding_model` is injected |
| `app.core.db.get_db_session` | DB session context manager | `episodic_memory.py` | Yes |
| `app.repositories.episode_repository.EpisodeRepository` | Episode persistence/retrieval logic | `episodic_memory.py` | Referenced but not provided |
| `app.agent.utils.llm.call_agent_llm` | LLM generation call | `summarizer.py`, `memory_extractor.py` (both lazy-imported) | Referenced but not provided |
| `app.agent.utils.parsing.extract_first_json_block` | Extracts a JSON block from raw LLM text output | `memory_extractor.py` | Referenced but not provided |
| `tiktoken` | Token counting/truncation | `token_counter.py` (optional — falls back gracefully) | No — has a built-in fallback |
| `app.core.config.settings` | `REDIS_URL`, `stm_ttl_seconds`, `stm_max_turns`, `qdrant_url`, `semantic_memory_collection`, `semantic_memory_top_k` | `short_term_memory.py`, `semantic_memory.py` | Referenced but not provided |

---

## Configuration

```env
# Short-term memory (Redis)
REDIS_URL=<your-redis-connection-url>          # settings.REDIS_URL
# settings.stm_ttl_seconds  — TTL for a session's key, refreshed on every write
# settings.stm_max_turns    — max stored turns per session (older turns trimmed)

# Semantic memory (Qdrant)
# settings.qdrant_url                 — Qdrant connection URL
# settings.semantic_memory_collection — collection name
# settings.semantic_memory_top_k      — default recall limit
```

Exact env var names for the `settings.*` attributes beyond `REDIS_URL` (which is referenced in uppercase directly) are `Not enough information from the provided code` — this file only shows the attribute access, not the underlying `Settings` class definition.

---

## Error Handling

The dominant pattern across this entire module is **fail-open**: nearly every read/write/delete operation catches broad exceptions, logs a warning, and returns a safe empty/default value rather than propagating the error — explicitly justified in `short_term_memory.py`'s docstring ("memory must never prevent a user from receiving an answer") and consistently applied in `semantic_memory.py` and `episodic_memory.py`.

Exceptions to this pattern:
* `SemanticMemory.store()` **raises `ValueError`** for an unsupported `memory_type` — this one validation failure is not swallowed, since it represents a programming/input error rather than an infrastructure failure.
* `ShortTermMemory.save()`'s Redis pipeline loop specifically distinguishes `WatchError` (retried in a loop, since it means another writer raced the same key) from all other exceptions (re-raised to the outer handler, which then logs and swallows it).
* `MemoryExtractor.extract_and_store()`'s per-item loop catches only `(TypeError, ValueError)` around each `store()` call — narrower than the blanket `except Exception` used elsewhere — so an unexpected error type from `store()` (e.g. a Qdrant connectivity error) would propagate out of the per-item loop rather than being silently skipped for that one item; whether that then propagates further depends on whether `SemanticMemory.store()` itself raises it uncaught, which it does not currently catch for infra errors (only the `ValueError` on invalid `memory_type` is explicitly raised by `store`; other exceptions inside `store`, such as a Qdrant connection failure during `upsert`, are not caught in `semantic_memory.py`'s `store()` method itself).

---

## Async / Background Processing

No task-queue or async code exists directly in this module. However, `SemanticMemory.prune_low_importance` and, by inference, some `MemoryExtractor`/`SessionSummarizer` invocation are the presumed logic behind the Celery tasks named in the previously-reviewed `celery` module's `task_routes` (`app.services.semantic_memory_service.prune_low_importance_semantic_memories`, `app.services.semantic_memory_service.extract_semantic_memory`, `app.services.episodic_memory_service.write_episode`). Those service-layer wrapper functions themselves are not part of this zip, so the exact call relationship between this module's classes and those Celery task names is `Not enough information from the provided code` — it is a plausible connection based on naming, not a confirmed one.

---

## Observability

Every class in this module uses the standard `logging` module (`logger = logging.getLogger(__name__)`), with a consistent severity convention:
* `logger.info(...)` — successful writes/reads that are noteworthy (e.g. `SemanticMemory.store`/`recall`, `EpisodicMemory.save_episode`).
* `logger.warning(...)` — every caught failure across all stores, always including the underlying exception via `%s`.
* `logger.debug(...)` — non-fatal index-creation failures in `SemanticMemory._ensure_collection`.

No metrics, tracing, or token/cost tracking is present in this module — `SessionSummarizer` and `MemoryExtractor` call an LLM but do not record token usage or cost themselves (that would depend on what `call_agent_llm` returns and whether the caller records it, both outside this zip).

---

## Security

* **Ownership verification:** `SemanticMemory.forget()` explicitly checks that the stored point's `tenant_id`/`user_id` match the caller's before deleting — a concrete, present authorization control at the data-access layer, not merely relying on the caller to have already checked.
* **Isolation via query filters:** `SemanticMemory.recall()`/`clear_user()` always filter by both `tenant_id` and `user_id`; `ShortTermMemory` isolates via key namespacing.
* **Prompt-level data-minimization instructions:** both `SessionSummarizer` and `MemoryExtractor` include explicit instructions in their LLM prompts not to retain "credentials," "secrets," or "chain-of-thought" — this is a prompt-level control (asking the LLM to comply), not a code-level filter verifying the LLM's output doesn't contain such data before storage. `Not implemented / not visible in the provided code`: any post-hoc validation that extracted/summarized content doesn't actually contain sensitive data despite the prompt instruction.
* **Content length bounding:** `SemanticMemory.store()` truncates stored `content` to 4000 characters before persisting, and `SessionSummarizer` truncates the conversation text fed into its prompt to 12,000 characters — both are hard caps, not validated against actual token limits of the target LLM.
* **The `prune_low_importance` global scope** (no tenant filter) is a deliberate cross-tenant operation by design (a maintenance task), not a leak — it only deletes based on `importance`, never reads or returns content across tenants.
* `Not implemented / not visible in the provided code`: authentication of the caller invoking any of these classes — that responsibility sits entirely with code not included in this zip.

---

## Performance

### Implemented Optimizations
* `ShortTermMemory.save()` uses a single atomic Redis pipeline (`WATCH`/`MULTI`/`EXEC`) to combine read, append, trim, and `SETEX` into one round-trip-safe operation, retrying only on `WatchError` rather than blindly retrying all failures.
* `SemanticMemory._ensure_collection` only creates the collection/indexes if they don't already exist (`collection_exists` check first), avoiding repeated creation calls on every write.
* `WorkingMemory.assemble()` stops adding items as soon as the token budget is exhausted rather than computing token counts for the entire candidate set first.
* `MemoryExtractor.extract_and_store()` caps extraction to at most 5 memories per interaction (`extracted[:5]`), bounding the number of embedding + upsert calls per completed Q&A turn.

### Potential Optimization Opportunities
* `ShortTermMemory._client()` constructs a **new Redis connection on every call** (`load`, `save`, `clear`, `clear_all`) rather than reusing a pooled/shared client — this is a concrete pattern visible in the code, not an inference; whether `redis.from_url` internally pools connections depends on the `redis` library's defaults, which is outside this file.
* `MemoryExtractor.extract_and_store()` instantiates a **new `SemanticMemory()` internally** rather than accepting an injected instance (unlike `SemanticMemory.__init__` itself, which supports injection) — this means each extraction call creates its own `QdrantClient`/`EmbeddedModel`, rather than reusing ones already constructed elsewhere in the request/task lifecycle.
* `SemanticMemory.recall()`'s re-ranking (`score * (0.5 + 0.5 * importance)`) is done client-side in Python after retrieval, not as a native Qdrant scoring/ordering feature — fine at the `top_k` sizes implied by typical recall limits, but not a database-level optimization.

---

## Failure Scenarios

| Failure | Expected Behavior | Impact |
|---|---|---|
| Redis unavailable (short-term memory) | Every method catches the exception, logs a warning, returns `[]`/`None`/`0` | Conversation history for that call is unavailable; the calling flow is not blocked (per the module's explicit design intent) |
| Concurrent short-term memory writer (Redis `WatchError`) | Retried in an internal loop until the transaction succeeds | Write eventually succeeds (or the outer `except` catches a non-`WatchError` failure) |
| Qdrant unavailable (semantic memory `recall`, `forget`, `clear_user`, `prune_low_importance`) | Caught, logged, returns `[]`/`False` | Semantic recall/deletion silently no-ops for that call |
| Qdrant unavailable (semantic memory `store`) | **Not caught inside `store()` itself** — no try/except wraps the embedding call or `self.client.upsert(...)` in this method | Exception propagates to the caller of `store()` (e.g. `MemoryExtractor`'s per-item loop, which only catches `TypeError`/`ValueError` — a Qdrant/network exception here would propagate further, out of `extract_and_store()` entirely, since no outer `except Exception` wraps the `store()` call in `memory_extractor.py`) |
| Invalid `memory_type` passed to `SemanticMemory.store()` | Raises `ValueError` | Not caught inside `store()`; caught by `MemoryExtractor`'s narrower `except (TypeError, ValueError)` when called from there, but would propagate if called directly by other, unprovided code |
| DB unavailable (episodic memory) | Every method catches the exception, logs a warning, returns `None`/`[]`/`0` | Episode save/read/clear silently no-ops |
| LLM call fails (`SessionSummarizer`, `MemoryExtractor`) | Caught, logged, returns `""`/`[]` | Summarization/extraction silently no-ops for that call |
| Malformed JSON from LLM (`MemoryExtractor`) | `json.loads`/`extract_first_json_block` failure caught by the surrounding `except Exception` | Returns `[]` — nothing extracted for that interaction |

---

## Testing

No tests were provided in the analyzed code.

---

## Deployment

No Dockerfiles, environment manifests, or startup scripts are included in the provided code. This module implies (via imports) a running Redis instance, a running Qdrant instance, and a reachable relational database (through `get_db_session`/`EpisodeRepository`) — but no deployment configuration confirming any of these is provided.

---

## Known Limitations

### Confirmed Limitations
* `ShortTermMemory._client()` creates a new Redis connection on every call rather than reusing a shared client.
* `SemanticMemory.store()` does not catch exceptions from the embedding call or the Qdrant upsert itself — only `MemoryExtractor`'s caller-side narrow exception handling provides any resilience, and even that would miss non-`TypeError`/`ValueError` failures (e.g. connectivity errors), letting them propagate.
* `SemanticMemory.prune_low_importance()` has no tenant/user scoping — it is a global operation by design, which is correct for its use as a scheduled maintenance task, but means it cannot be safely called per-tenant without modification.
* `MemoryExtractor` always constructs its own `SemanticMemory()` instance rather than accepting one via dependency injection, unlike `SemanticMemory` itself which supports client/embedding-model injection.
* `EpisodicMemory`'s actual tenant/user isolation guarantees cannot be verified from this zip, since all filtering logic lives inside the unprovided `EpisodeRepository`.

### Potential Risks / Improvements
* Consider wrapping `SemanticMemory.store()`'s embedding/upsert calls in the same fail-open `try/except` pattern used by its own `recall`/`forget`/`clear_user`/`prune_low_importance` methods, for consistency and resilience.
* Consider injecting a shared Redis client into `ShortTermMemory` rather than constructing one per call, if connection overhead becomes a measured concern.
* Consider allowing `MemoryExtractor` to accept an injected `SemanticMemory` instance for consistency with the rest of the module's dependency-injection pattern.

---

## Summary

This module implements Atlas AI's four-layer memory system: `ShortTermMemory` (Redis, tenant/user/session-namespaced keys, atomic bounded-history writes, fully fail-open), `SemanticMemory` (Qdrant, tenant+user-filtered vector recall blended with a stored importance score, explicit ownership checks on deletion, mostly fail-open except for input validation and the `store()` write path itself), `EpisodicMemory` (a thin, fail-open wrapper delegating all persistence and isolation logic to an unprovided `EpisodeRepository`), and `WorkingMemory` (a non-persistent, priority-ordered, token-budgeted context assembler). Two supporting LLM-driven utilities — `SessionSummarizer` and `MemoryExtractor` — turn raw conversation turns and completed Q&A interactions into durable episodic/semantic memories respectively, both using explicit prompt-level instructions to avoid retaining secrets or chain-of-thought, and both fail-open on LLM or parsing errors. A `TokenCounter` utility backs `WorkingMemory`'s budget enforcement, using `tiktoken` when available and a character-based approximation otherwise. The consistent design principle across nearly the entire module — stated explicitly in `short_term_memory.py`'s docstring and observed consistently in the other files — is that memory subsystem failures must degrade gracefully rather than block the user-facing response, with the notable exception of `SemanticMemory.store()`'s own infrastructure-error handling, which is not wrapped in the same fail-open pattern used elsewhere in that class.
