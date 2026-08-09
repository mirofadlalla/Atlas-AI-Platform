# Atlas AI — Agent Module

## Overview

This module implements the reasoning/orchestration **agent** for Atlas AI: a LangGraph state machine that takes a user question, decomposes it if necessary, decides between two tools (SQL over a Postgres database, and RAG-style document retrieval), gathers evidence, and produces a grounded final answer. It integrates with short-term/semantic/episodic memory subsystems, Redis-based caching, Prometheus metrics, lightweight tracing, and multi-tenant SQL isolation.

**Scope of this documentation:** only the code under the `agent/` package provided in the uploaded archive. Several modules the agent imports (`app.memory.*`, `app.services.*`, `app.rag.steps.retriever`, `app.core.db`, `app.core.config`, `app.design_pattern.llm_singlton.LLMService`) are **referenced but not provided**, so their internal behavior is documented only to the extent it can be inferred from how the agent calls them — never assumed.

## Responsibilities

- Own the multi-step reasoning loop (LangGraph `StateGraph`) that decides *when* to query the database, *when* to retrieve documents, and *when* to stop.
- Decompose compound questions into sub-questions and answer them one at a time, then synthesize a final answer.
- Enforce SQL safety (SELECT-only, tenant filtering, allow-lists, cost limits, timeouts) before any query touches the database.
- Wrap all outbound LLM/DB calls with retries, timeouts, and circuit breakers.
- Read/write conversational, semantic, and episodic memory around each run (delegated to `app.memory` / `app.services`, not shown here).
- Emit structured logs, Prometheus metrics, and lightweight trace spans for every graph node.

## Boundaries — what this module does *not* do

- It does not implement the memory backends themselves (`ShortTermMemory`, `SemanticMemory`, `EpisodicMemory`, `WorkingMemory` are imported from `app.memory.*` but their code is not in this archive).
- It does not implement the vector retriever (`get_retriever` is imported from `app.rag.steps.retriever`).
- It does not implement the LLM client (`LLMService` is imported from `app.design_pattern.llm_singlton`).
- It does not own DB connectivity/session creation (`get_db_session`, `data_base` come from `app.core.db`).
- It is not the API layer — no FastAPI routes are included in this archive; nothing in the provided code shows how a request enters `agent_app`.

## Dependencies (what this module depends on)

- `langgraph` (graph orchestration), `langchain_core` (output parser), `pydantic` / `pydantic_settings`.
- `sqlglot` (AST-based SQL parsing/validation), `sqlalchemy` (schema inspection, session, `text()` execution).
- `redis` (optional, imported lazily inside try/except — retrieval cache and run idempotency cache).
- `tenacity` (retry backoff).
- `prometheus_client` (metrics).
- `groq` (optional import, only used to widen the retryable-exception tuple).
- External, not-provided `app.*` modules listed above.

## What depends on this module

Not enough information from the provided code — no callers of `agent_app` (e.g., API routes, Celery tasks) are included in this archive. `agent/__init__.py` lazily exposes `agent_app` via `__getattr__`, which is the only visible integration point.

## Project Structure

```text
agent/
├── __init__.py                 # Lazy export of agent_app
├── schemas.py                  # ActionDecision pydantic model + JSON format instructions
├── core/
│   ├── config.py                # AgentSettings (env-driven, prefix AGENT_)
│   ├── state.py                 # AgentState TypedDict (LangGraph state schema)
│   ├── graph.py                 # StateGraph wiring: nodes + edges + compile()
│   └── router.py                # route_action / route_after_finish conditional routing
├── nodes/
│   ├── __init__.py               # All node coroutines (memory_read, recall, decompose,
│   │                              # think, sql_tool, retrieval_tool, finish, memory_write)
│   └── finish_helpers.py         # answer_subquestion / synthesize_final_answer helpers
├── tools/
│   ├── base.py                    # AgentTool ABC, ToolResult/ToolObservation, ToolRegistry
│   ├── retrieval.py                # Re-exports get_retriever from app.rag.steps.retriever
│   ├── retrieval_cache.py          # Redis-backed cache for retrieval results
│   ├── retrieval_tool.py           # RetrievalTool (AgentTool implementation)
│   ├── sql_tool.py                 # SQLTool (AgentTool implementation)
│   └── sql_engine/
│       ├── schema_provider.py        # Cached, allow-list-aware DB schema introspection
│       ├── sql_generator.py          # LLM-based NL→SQL generation (SELECT-only)
│       └── validator.py              # sqlglot AST validation + tenant predicate injection
├── prompts/
│   └── registry.py                # All prompt templates (PromptRegistry)
├── observability/
│   ├── logging.py                 # log_node_event structured logging helper
│   ├── metrics.py                 # Prometheus Counters/Histograms
│   └── tracing.py                 # In-process Span/trace_span context manager
├── utils/
│   ├── circuit_breaker.py          # CircuitBreaker class; llm_circuit_breaker, db_circuit_breaker
│   ├── classification.py           # Keyword-based question-type classifier (data vs knowledge)
│   ├── context_budget.py           # Token/char budget truncation helpers (used in nodes)
│   ├── db_session.py               # Re-exports get_db_session as agent_db_session
│   ├── guardrails.py               # Prompt-injection phrase filter + numeric grounding check
│   ├── llm.py                      # call_agent_llm: timeout + circuit breaker + cost/usage metrics
│   ├── parsing.py                  # extract_first_json_block (robust JSON extraction from LLM text)
│   ├── result_formatting.py        # format_sql_results (row formatting/truncation for prompts)
│   ├── retry.py                    # with_retry (tenacity wrapper)
│   ├── run_cache.py                # Redis-backed idempotency cache for completed runs
│   ├── state_helpers.py            # create_initial_state, budget checks, per-subquestion reset
│   ├── state_transitions.py        # Sub-question advance / synthesis-decision helpers
│   └── token_budget.py             # truncate_context/estimate_chars — **appears unused/orphaned** (see Known Limitations)
└── eval/
    └── harness.py                 # Offline evaluation of classify_question_type and JSON extraction
```

## How It Works — High-Level Architecture

```text
                         ┌────────────────────┐
                         │   agent_app         │  (compiled LangGraph, exported from
                         │  (StateGraph)        │   agent/core/graph.py)
                         └─────────┬───────────┘
                                   │
              ┌────────────────────┼─────────────────────┐
              ▼                    ▼                      ▼
      ┌───────────────┐   ┌────────────────┐     ┌─────────────────┐
      │ Memory nodes   │   │  Reasoning loop │     │  Tools            │
      │ read/recall/   │   │  decompose→think│     │  SQLTool          │
      │ write          │   │  →(sql|retrieve │     │  RetrievalTool     │
      └───────┬────────┘   │   |finish)→loop │     └────────┬──────────┘
              │             └────────┬───────┘              │
              ▼                      ▼                      ▼
  app.memory.* (not provided)   Redis (idempotency,     app.core.db (SQLAlchemy),
  app.services.* (not provided) retrieval cache)         app.rag.steps.retriever (not provided)
```

Every node is wrapped by `_run_node` (in `agent/nodes/__init__.py`), which:
1. Opens a `trace_span` (observability/tracing.py) tagged with `run_id`/`tenant_id`.
2. Checks `budget_exceeded_update(state)` first — if the run has timed out or exceeded step/sub-question limits, the node short-circuits and returns a `degraded` state update without doing any work.
3. Executes the node's inner logic.
4. On exception, logs and re-raises (LangGraph will surface it to the caller — no top-level catch-all is visible in this code).
5. In a `finally` block, increments `agent_node_executions_total` and observes `agent_node_duration_seconds`, regardless of success/failure.

## Request Lifecycle (Graph Execution Order)

The graph is defined in `agent/core/graph.py`. Entry point: `memory_read`. Compiled object: `agent_app` (a LangGraph `CompiledGraph`), invoked via LangGraph's standard `.invoke()`/`.ainvoke()` (not shown in this archive — no route/caller is provided).

```text
START
  │
  ▼
[memory_read]        → ShortTermMemory().load(tenant_id, user_id, session_id) → conversation_history
  │
  ▼
[episodic_recall]     → EpisodicMemory().get_recent(user_id, tenant_id, exclude_session_id) → episode_context
  │
  ▼
[semantic_recall]     → SemanticMemory().recall(question, user_id, tenant_id) → recalled_memories
  │
  ▼
[decompose]           → LLM call (tier="routing") → sub_questions[], resets sub_answers/index
  │
  ▼
[think]  ◄─────────────────────────────────────────────────────┐
  │  LLM call (tier="routing") → ActionDecision{thought, action}│
  │                                                              │
  ├── action == "sql"  ──────► [sql_tool] ─────────────────────►┤ (edge: sql_tool → think)
  │                                                              │
  ├── action == "retrieval" ─► [retrieval_tool] ────────────────┤ (edge: retrieval_tool → think)
  │                                                              │
  └── action == "finish" (or routed there by route_action) ─────┘
              │
              ▼
        [finish]  → answer_subquestion() (LLM, tier="generation")
              │
              ├── more sub-questions remain → route_after_finish → back to [think]
              │
              └── last sub-question answered → synthesize_final_answer() if multiple
                          │  sub-questions (LLM, tier="generation")
                          ▼
                  [memory_write] → ShortTermMemory().save(...) x2 (user + assistant turns)
                                    trigger_semantic_memory_extraction(...)
                                    trigger_episode_write(...)
                          │
                          ▼
                         END
```

This diagram reflects the exact edges declared in `agent/core/graph.py`: `memory_read → episodic_recall → semantic_recall → decompose → think`, then conditional edges from `think` (via `route_action`) to `sql_tool` / `retrieval_tool` / `finish`, `sql_tool → think`, `retrieval_tool → think`, and conditional edges from `finish` (via `route_after_finish`) to `think` (more sub-questions) or `memory_write` (done) → `END`.

## Agent Graph — Detailed Node Reference

| Node | File | Type | Purpose |
|---|---|---|---|
| `memory_read` | `nodes/__init__.py` | async | Loads prior conversation turns via `ShortTermMemory().load()` |
| `episodic_recall` | `nodes/__init__.py` | async | Loads recent session summaries via `EpisodicMemory().get_recent()`, excluding the current session |
| `semantic_recall` | `nodes/__init__.py` | async | Recalls durable user facts via `SemanticMemory().recall()` |
| `decompose` | `nodes/__init__.py` | async, wrapped by `_run_node` | LLM call to split the question into `sub_questions`; falls back to `[question]` on any parse/LLM failure; caps at `agent_settings.max_subquestions`, marking the run `degraded` if trimmed |
| `think` | `nodes/__init__.py` (`thought_node`) | async, wrapped by `_run_node` | LLM call producing an `ActionDecision` (`sql` / `retrieval` / `finish`); on LLM failure, forces `finish` and marks `degraded` |
| `sql_tool` | `nodes/__init__.py` (`sql_node`) | async, wrapped by `_run_node` | Runs `SQLTool.run()` in a thread, merges `ToolResult` into state via `_apply_tool_result` |
| `retrieval_tool` | `nodes/__init__.py` (`retrieval_node`) | async, wrapped by `_run_node` | Runs `RetrievalTool.run()` in a thread, merges result into state |
| `finish` | `nodes/__init__.py` (`finish_node`) | async, wrapped by `_run_node` | Calls `answer_subquestion()`; if this is the last sub-question, also calls `synthesize_final_answer()` (only when more than one sub-question exists) |
| `memory_write` | `nodes/__init__.py` | async | Persists the user+assistant turn, and fires (not awaited — see Async Processing) semantic-memory extraction and episodic-summary writing |

### Conditional Routing — `route_action` (agent/core/router.py)

Called after every `think` node execution. Decision order (first match wins):

1. `degraded and last_action == "finish"` → `finish`.
2. `step_count >= max_steps_per_subquestion` → `finish`.
3. `last_action` not a registered tool and not `"finish"` → `finish` (safety fallback for malformed decisions).
4. Last two entries of `observation_history` are identical → `finish` (stuck-loop detection).
5. `_detect_action_loop(action_history)` — detects (a) immediate repeat of the same action, (b) an A-B-A-B oscillation over the last 4 actions, (c) a repeated 3-action pattern over the last 6 actions (window size configurable via `loop_detection_window`) → `finish`.
6. `last_action == "sql"` and `sql_has_results` → `finish` (success, no need to keep looping).
7. `last_action == "retrieval"` and has retrieval data → `finish`.
8. `last_action == "sql"`, SQL was attempted, no results → falls back to `retrieval` if retrieval hasn't been tried yet, else `finish`.
9. `last_action == "retrieval"`, retrieval attempted, no data → `finish`.
10. `last_action == "finish"` but heuristic classification says otherwise: if `classify_question_type` says `"data"` and no SQL results yet, force `"sql"`; if `"knowledge"` and no retrieval data yet, force `"retrieval"`.
11. Default: return `last_action` unchanged (keep looping on the same tool if none of the above apply).

### Conditional Routing — `route_after_finish`

Compares `current_sub_question_index` against `len(sub_questions)`. If sub-questions remain, routes back to `think`; otherwise routes to `end` (which the graph maps to `memory_write`).

### Termination Conditions

- All sub-questions answered (`route_after_finish` → `end`).
- Step budget: `max_steps_per_subquestion` (default 6), enforced in `route_action`.
- Global budget: `max_total_steps` (default 50) and `agent_timeout_seconds` (default 120s), enforced by `budget_exceeded_update` inside `_run_node`, checked before every node body runs.
- Sub-question count cap: `max_subquestions` (default 10), enforced in `decompose_node` (truncates and marks degraded) and again in `budget_exceeded`.
- Loop detection (see routing rule 5 above).

### Retries / Error Paths in the Graph

- `decompose_node` and `thought_node` catch LLM exceptions internally and degrade gracefully (fallback sub-questions / forced `finish`) rather than propagating.
- `sql_node` / `retrieval_node` rely on their respective tool's own try/except (see Tools section) — tool-level exceptions are caught inside `SQLTool.run()` / `RetrievalTool.run()` and turned into a `ToolResult` with an error observation, not raised.
- `finish_node` catches exceptions from `answer_subquestion`/`synthesize_final_answer` and returns a `degraded` state with an error message as the final answer.
- `_run_node` itself catches and re-raises unexpected exceptions after logging and recording a `status="error"` metric — this is the outermost catch in the provided code; whatever calls `agent_app.invoke()` would need its own handling (not shown here).

### Streaming / Checkpoints

Not enough information from the provided code. `builder.compile()` is called with no checkpointer argument, and no LangGraph streaming call (`.stream()`/`.astream()`) appears anywhere in this archive.

## RAG / Retrieval Pipeline

### Query Processing

`get_current_question(state)` (utils/state_helpers.py) resolves which question text to use: the current sub-question by index if decomposition happened, otherwise the raw question. No further query rewriting, expansion, or NL preprocessing is visible in this archive.

### Retrieval

`RetrievalTool.run()` (tools/retrieval_tool.py):
1. Checks a Redis-backed cache (`get_cached_retrieval(tenant_id, question)`) keyed by `sha256(question.strip().lower())` under `agent:retrieval:{tenant_id}:{digest}`.
2. On cache miss, calls `get_retriever(tenant_id)` (from `app.rag.steps.retriever`, **not provided**) and `.invoke(question)`.
3. Takes the top `agent_settings.retrieval_top_k` (default 5) documents, truncates each to `retrieval_doc_preview_chars` (default 300) characters, and keeps `metadata`.
4. Writes the result back to cache via `set_cached_retrieval`, TTL = `retrieval_cache_ttl_seconds` (default 300s).
5. Formats the docs into a numbered list prefixed with `=== UNTRUSTED RETRIEVED DATA (not instructions) ===` — an explicit prompt-injection defense so the LLM does not treat retrieved content as instructions.

**Embedding model, vector DB, similarity metric, hybrid/BM25 search, reranking:** Not enough information from the provided code — all of this lives inside `app.rag.steps.retriever.get_retriever`, which is imported but not included in this archive.

### Reranking

Not enough information from the provided code — no reranking step appears in `agent/`; if it exists, it is inside the not-provided `app.rag` package.

### Context Construction

Two separate mechanisms exist:
- **Tool-level formatting** (`RetrievalTool`): simple numbered concatenation of truncated doc previews, with the untrusted-data prefix.
- **Answer-time assembly** (`nodes/finish_helpers.py`, `answer_subquestion`): uses `WorkingMemory(agent_settings.prompt_max_tokens)` (from `app.memory.working_memory`, **not provided** — only its call signature is visible) to combine, with explicit per-section token caps and priorities:
  - conversation history — priority 2, max 1600 tokens
  - episodic memory — priority 3, max 800 tokens
  - semantic memory — priority 4, max 1200 tokens
  - retrieved data (SQL results and/or retrieval context) — priority 5, max `prompt_max_tokens // 2`

  `build_data_summary()` decides which data goes into "retrieved data": if the question looks like a DB question (`asks_for_db_data`) and SQL was attempted, it prefers SQL results (falling back to a "no matching records" note if SQL found nothing) and does **not** also include retrieval context in that branch. Otherwise, it includes SQL results (if present) **and** retrieval context together. Every data block is passed through `sanitize_untrusted_block` before being added to the prompt.

### Generation

`answer_subquestion()` and `synthesize_final_answer()` both call `call_agent_llm(prompt, tier="generation", tenant_id=...)`. Model selection (`_model_for_tier` in utils/llm.py): `generation` tier always uses `agent_settings.llm_generation_model` (default `llama-3.3-70b-versatile`). System prompt, temperature, and max tokens all come from `AgentSettings` (`llm_system_prompt`, `llm_temperature` default `1.0`, `llm_max_tokens` default `2048`) and are passed uniformly to every call regardless of tier — no per-tier temperature/system-prompt override is visible in this code. After generation, `validate_answer_grounding` checks whether numeric values in the answer appear in the source data; if not, it appends a caveat note to the answer (it does not block or regenerate the answer).

### Complete RAG-Adjacent Flow (as implemented)

```text
current_question
    │
    ▼
retrieval cache (Redis) ── hit ──► docs_payload
    │ miss
    ▼
get_retriever(tenant_id).invoke(question)  [app.rag.steps.retriever — not provided]
    │
    ▼
top-k truncation + preview char cap → docs_payload → cache write
    │
    ▼
"=== UNTRUSTED RETRIEVED DATA ===" + numbered doc list → retrieval_context (state)
    │
    ▼
(in finish node) build_data_summary → sanitize_untrusted_block → WorkingMemory.assemble()
    │
    ▼
prompt_registry.answer_subquestion(...) → call_agent_llm(tier="generation")
    │
    ▼
validate_answer_grounding → sub-question answer
```

## Memory System

The agent module **calls** four memory layers but does **not implement** them — their classes live in `app.memory.*` / `app.services.*`, which are not present in this archive. What is visible is exactly how/when the agent calls them:

| Layer | Class (not provided) | Read call | Write call | Where |
|---|---|---|---|---|
| Short-term / conversation | `ShortTermMemory` | `.load(tenant_id, user_id, session_id)` in `memory_read_node` | `.save(tenant_id, user_id, session_id, ConversationTurn(role, content, ""))` (called twice — user turn, assistant turn) in `memory_write_node` | `nodes/__init__.py` |
| Semantic (durable user facts) | `SemanticMemory` | `.recall(question, user_id, tenant_id)` in `semantic_recall_node` | Not called directly — extraction is delegated to `trigger_semantic_memory_extraction(question, final_answer, user_id, tenant_id)` from `app.services.semantic_memory_service` | `nodes/__init__.py` |
| Episodic (session summaries) | `EpisodicMemory` | `.get_recent(user_id, tenant_id, exclude_session_id)` in `episodic_recall_node` | Delegated to `trigger_episode_write(session_id, full_turn_history, user_id, tenant_id)` from `app.services.episodic_memory_service` | `nodes/__init__.py` |
| Working (prompt assembly buffer) | `WorkingMemory` | Instantiated per `answer_subquestion` call with `prompt_max_tokens`, `.add(...)` called per section, `.assemble()` returns final text | Not persistent — scoped to a single LLM call | `nodes/finish_helpers.py` |

### Tenant / User / Session Isolation

Every memory read/write call in this archive passes `tenant_id` and `user_id` (and `session_id` where relevant) as explicit arguments sourced from `AgentState`. **The actual isolation mechanism (DB filtering, Redis key namespacing, etc.) is implemented inside the not-provided `app.memory.*` classes.** This code proves that tenant/user/session identifiers are *threaded through* to those calls consistently, but it does **not** prove how (or whether) those classes enforce isolation internally.

### Failure Behavior

No try/except wraps the memory node calls in `nodes/__init__.py` (`memory_read_node`, `semantic_recall_node`, `episodic_recall_node`, `memory_write_node` are *not* wrapped by `_run_node`/its budget-and-metrics logic either — they are plain async functions called directly as graph nodes). This means: **if a memory backend raises, the graph run fails** — there is no visible graceful-degradation path for memory access, unlike the LLM/tool nodes which each have explicit fallback logic.

## Caching

Two independent Redis-backed caches exist in this module (both fail open — see below):

### Retrieval Cache (`tools/retrieval_cache.py`)

- **What is cached:** the top-k truncated document previews + metadata (`docs_payload`), as JSON.
- **Key:** `agent:retrieval:{tenant_id}:{sha256(question.strip().lower())}`.
- **TTL:** `agent_settings.retrieval_cache_ttl_seconds` (default 300s).
- **Hit behavior:** skips the call to `get_retriever(...).invoke(question)` entirely — so a cache hit bypasses whatever embedding/vector-search work happens inside the not-provided retriever.
- **Miss/failure behavior:** any exception (including Redis being unreachable, or the `redis` package not being installed) is caught and logged at debug level; the function returns `None` and the caller proceeds as a cache miss. This is a fail-open design — Redis unavailability degrades performance, not correctness.

### Run Idempotency Cache (`utils/run_cache.py`)

- **What is cached:** an arbitrary `dict[str, Any]` result, keyed by `run_id`, under `agent:run:complete:{run_id}`.
- **TTL:** `agent_settings.run_idempotency_ttl_seconds` (default 3600s).
- **Gate:** controlled by `agent_settings.run_idempotency_enabled` (default `True`) — when `False`, both get/set are no-ops.
- **Important:** `get_cached_run_result` / `cache_run_result` are defined but **not called anywhere else in this archive** (no reference in `graph.py` or `nodes/`). Not enough information from the provided code to say where/if run idempotency is actually applied — it may be wired up in a not-provided API layer, or it may be dead code (see Known Limitations).
- Fails open the same way as the retrieval cache.

### Schema Cache (`tools/sql_engine/schema_provider.py`)

Not Redis — an in-process module-level dict (`_cache`). Caches the DB schema description text keyed by `sql_namespace` (or `"__all__"`), TTL = `schema_cache_ttl_seconds` (default 300s). A cache hit skips SQLAlchemy `inspect(data_base)` schema introspection entirely, avoiding a DB round-trip on every SQL-generation call. `invalidate_schema_cache()` is provided but not called anywhere in this archive.

### What a cache hit bypasses, per cache

| Cache | Bypasses on hit |
|---|---|
| Retrieval cache | Vector retriever invocation (embedding + similarity search + whatever reranking may live inside it) |
| Schema cache | SQLAlchemy schema introspection (`inspector.get_table_names()`/`get_columns()`) |
| Run idempotency cache | Not applicable — not currently invoked anywhere in this code |

None of the caches bypass the LLM generation call itself; there is no semantic or exact-match cache over LLM responses in this archive.

## Multi-Tenancy

### Tenant Identification & Propagation

`tenant_id` enters as a field of `AgentState`, set at run creation via `create_initial_state(question, tenant_id, ...)` (utils/state_helpers.py). From there it is threaded explicitly through: memory reads/writes, `call_agent_llm(..., tenant_id=...)` (for cost/usage metric labeling), `RetrievalTool` (cache key + `get_retriever(tenant_id)`), and `SQLTool` → `SQLValidator.validate_and_enforce_tenant(sql, tenant_id)`.

### Database-Level Enforcement (the strongest guarantee in this code)

`SQLValidator.validate_and_enforce_tenant` (tools/sql_engine/validator.py):
1. Parses the LLM-generated SQL with `sqlglot` (dialect `postgres`).
2. Rejects anything that isn't a bare `Select`/`Union` AST, and separately walks the tree rejecting `Insert/Update/Delete/Drop/Alter/Create/TruncateTable/Merge/Command` nodes.
3. Rejects multiple statements (checks for a stray `;`).
4. If `allowed_tables`/`allowed_columns` are configured (via `AGENT_SQL_NAMESPACE` / `AGENT_SQL_ALLOWED_COLUMNS`), rejects queries referencing disallowed tables/columns.
5. **Injects a parameterized `tenant_id = :tenant_id` predicate into the `WHERE` clause of every `Select` node** (ANDed with any existing predicate), via a `sqlglot` AST transform — not a string-concatenation filter. The prompt explicitly instructs the SQL-generation LLM *not* to add its own `tenant_id` filter, since it's injected automatically.
6. The actual value is bound as a SQLAlchemy parameter (`params = {"tenant_id": tenant_id}`), not interpolated into the SQL string, protecting against SQL injection in the tenant predicate itself.

### Where boundaries are enforced (per component)

```text
Request → AgentState.tenant_id
    → SQLTool: enforced in SQL AST (validator.py) — strong, structural guarantee
    → RetrievalTool: passed to get_retriever(tenant_id) — enforcement mechanism is
      inside the not-provided app.rag.steps.retriever; not verifiable from this code
    → Retrieval cache key includes tenant_id — prevents cross-tenant cache reuse
    → Memory layers: tenant_id/user_id passed as arguments — enforcement mechanism
      is inside not-provided app.memory.* classes; not verifiable from this code
    → Metrics: tenant_id used only as a Prometheus label (agent_llm_tokens_total,
      agent_llm_cost_usd_total) — for observability, not access control
```

### Authentication / Authorization

Not enough information from the provided code — no authentication or authorization logic is present in `agent/`. `tenant_id`/`user_id` are trusted inputs to `create_initial_state`; how they were validated upstream (JWT, session, etc.) is outside this archive.

## Data Flow — Key State Objects

`AgentState` (agent/core/state.py) is a single `TypedDict` (`total=False`) that flows through every graph node as both input and output (LangGraph merges each node's returned `dict` into the accumulated state). Key groups of fields:

```text
Identity/session:      question, tenant_id, user_id, session_id, run_id, start_time
Memory inputs:          conversation_history, recalled_memories, episode_context, working_memory_tokens, context_sources
Reasoning trace:        thought, thoughts, last_action, observation, observation_history, action_history
Tool state:              last_sql, sql_result, sql_attempted, sql_has_results,
                          retrieval_context, retrieval_attempted, retrieval_has_results
Loop/budget counters:    step_count, total_step_count, total_cost, llm_cost_usd, input_tokens, output_tokens
Decomposition:           original_question, sub_questions, sub_answers (list[SubAnswer]), current_sub_question_index
Output:                  final_answer, degraded, degraded_reason, data_sources, tool_observations
```

`SubAnswer` is a nested `TypedDict` with `question` and `answer` string fields, appended to `sub_answers` by `append_sub_answer` after each sub-question is resolved.

### Data Flow Diagram (implementation-specific)

```text
question (initial state)
    │
    ▼
sub_questions[]  (decompose_node; falls back to [question] on failure)
    │
    ▼  (loop per sub-question, index tracked by current_sub_question_index)
current_question = get_current_question(state)
    │
    ▼
ActionDecision (think) ──► ToolResult (sql_tool | retrieval_tool) ──► state_updates merged
    │                                                                  (last_sql/sql_result/
    │                                                                   retrieval_context, etc.)
    ▼
data_summary_text, data_sources = build_data_summary(state, current_question)
    │
    ▼
assembled_context = WorkingMemory(...).add(...).assemble()
    │
    ▼
sub_answer_text = LLM(answer_subquestion prompt) → validate_answer_grounding
    │
    ▼
sub_answers.append(SubAnswer(question, answer))
    │
    ▼ (if last sub-question)
final_answer = sub_answer_text  (single sub-question)
             | LLM(synthesize_final prompt over all sub_answers)  (multiple)
    │
    ▼
memory_write_node persists (question, final_answer) turn + triggers semantic/episodic writes
```

## External Dependencies

| Dependency | Purpose | Where Used | Required? |
|---|---|---|---|
| PostgreSQL (via SQLAlchemy) | Source of truth queried by SQLTool; schema introspection | `sql_engine/schema_provider.py`, `sql_engine/validator.py` (via `app.core.db`, not provided) | Required for the `sql` action path; agent can still function via `retrieval` if DB is unavailable, subject to routing logic |
| Redis | Retrieval result cache, run idempotency cache | `tools/retrieval_cache.py`, `utils/run_cache.py` | Optional/fail-open — code catches all exceptions and treats Redis absence as a cache miss |
| LLM provider (Groq, `llama-3.3-70b-versatile` by default) | Decompose, thought/routing, SQL generation, sub-question answering, final synthesis | `utils/llm.py` → `app.design_pattern.llm_singlton.LLMService` (not provided) | Required — every reasoning step depends on an LLM call |
| Vector retriever / RAG backend | Document retrieval for the `retrieval` action | `tools/retrieval.py` → `app.rag.steps.retriever.get_retriever` (not provided) | Required for the `retrieval` action path |
| Memory services (`app.memory.*`, `app.services.*`) | Conversation, semantic, episodic, working memory | `nodes/__init__.py`, `nodes/finish_helpers.py` | Required — no fallback path if these raise (see Memory System → Failure Behavior) |
| Prometheus (`prometheus_client`) | Metrics collection | `observability/metrics.py` | Required at import time (module-level `Counter`/`Histogram` construction) — no try/except around it |
| `sqlglot` | SQL AST parsing/validation, tenant predicate injection | `tools/sql_engine/validator.py` | Required for the `sql` action path |
| `tenacity` | Retry/backoff wrapper | `utils/retry.py` | Required — imported unconditionally |

## Configuration

All configuration is centralized in `agent/core/config.py` as `AgentSettings` (pydantic-settings `BaseSettings`), loaded from environment variables with prefix `AGENT_` and an optional `.env` file. Unknown env vars are ignored (`extra="ignore"`).

```env
# Step / loop budgets
AGENT_MAX_STEPS_PER_SUBQUESTION=6
AGENT_MAX_SUBQUESTIONS=10
AGENT_MAX_TOTAL_STEPS=50
AGENT_AGENT_TIMEOUT_SECONDS=120.0
AGENT_LOOP_DETECTION_WINDOW=6

# SQL tool
AGENT_SQL_QUERY_TIMEOUT_SECONDS=30.0
AGENT_SQL_MAX_ROWS=1000
AGENT_SQL_MAX_RESULT_ROWS_IN_PROMPT=20
AGENT_SQL_MAX_ALLOWED_COST=1000.0
AGENT_SQL_COST_UNKNOWN_DEFAULT=1001.0
AGENT_SQL_NAMESPACE=                 # comma-separated allow-listed table names; empty = all tables
AGENT_SQL_ALLOWED_COLUMNS=           # comma-separated allow-listed column names; empty = all columns
AGENT_SCHEMA_CACHE_TTL_SECONDS=300

# Retrieval
AGENT_RETRIEVAL_CACHE_TTL_SECONDS=300
AGENT_RETRIEVAL_TOP_K=5
AGENT_RETRIEVAL_DOC_PREVIEW_CHARS=300

# LLM
AGENT_LLM_RETRY_ATTEMPTS=3
AGENT_LLM_RETRY_MIN_WAIT_SECONDS=0.5
AGENT_LLM_RETRY_MAX_WAIT_SECONDS=4.0
AGENT_LLM_TIMEOUT_SECONDS=45.0
AGENT_LLM_MAX_TOKENS=2048
AGENT_LLM_TEMPERATURE=1.0
AGENT_LLM_SYSTEM_PROMPT="You are a helpful assistant."
AGENT_LLM_ROUTING_MODEL=              # empty → falls back to generation model
AGENT_LLM_GENERATION_MODEL=llama-3.3-70b-versatile
AGENT_LLM_INPUT_COST_PER_MILLION=0.59
AGENT_LLM_OUTPUT_COST_PER_MILLION=0.79
AGENT_PROMPT_MAX_TOKENS=12000

# Resilience
AGENT_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
AGENT_CIRCUIT_BREAKER_RECOVERY_SECONDS=60.0

# Idempotency
AGENT_RUN_IDEMPOTENCY_ENABLED=true
AGENT_RUN_IDEMPOTENCY_TTL_SECONDS=3600
```

Additionally, `REDIS_URL` is consumed via `app.core.config.settings` (not provided — the exact env var name for this global settings object is not visible in this archive, only that `settings.REDIS_URL` is read directly by `retrieval_cache.py` and `run_cache.py`).

**Never commit real credentials.** No secrets appear directly in the provided code — `REDIS_URL` and DB connection details are sourced from the not-provided `app.core.config`/`app.core.db` modules.

## API Reference

Not enough information from the provided code — no HTTP route definitions (FastAPI or otherwise) are present in this archive. The only public entry point visible is `agent_app` (a compiled LangGraph object, exported lazily from `agent/__init__.py`), which would be invoked by an external caller not included here.

## Error Handling Summary

| Component | Failure | Behavior |
|---|---|---|
| `decompose_node` | LLM call/JSON parse fails | Falls back to `sub_questions = [question]`; run continues undegraded (this specific failure alone does not set `degraded`) |
| `thought_node` | LLM call fails | Forces `last_action = "finish"`, sets `degraded=True`, `degraded_reason="LLM call failed during reasoning"` |
| `SQLTool.run` | `ValueError` (validation) | Returns `ToolResult` with error observation, `sql_attempted=True`, `sql_has_results=False` — no exception propagates to the graph |
| `SQLTool.run` | Any other exception (execution) | Same graceful degrade pattern, generic error message |
| `RetrievalTool.run` | Any exception | Same graceful degrade pattern (`retrieval_attempted=True`, `retrieval_has_results=False`) |
| `finish_node` | Exception in `answer_subquestion`/`synthesize_final_answer` | Returns `final_answer` containing the error text, `degraded=True` |
| `memory_read_node` / `semantic_recall_node` / `episodic_recall_node` / `memory_write_node` | Any exception | **Not caught** — propagates and fails the graph run (these nodes are not wrapped by `_run_node`) |
| `call_agent_llm` | Timeout | `ThreadPoolExecutor` future times out after `llm_timeout_seconds` → raises `TimeoutError`, which is one of the retryable exceptions in `with_retry` (via `_retryable_exceptions`) |
| `call_agent_llm` | Repeated failures | `llm_circuit_breaker` opens after `circuit_breaker_failure_threshold` consecutive failures, then raises `RuntimeError` immediately for `circuit_breaker_recovery_seconds` without attempting the call |
| `SQLValidator.explain_and_execute` | DB errors | Routed through `db_circuit_breaker`, same open/half-open/closed behavior as the LLM breaker |
| `SQLValidator.get_query_cost` | `EXPLAIN` fails | Fails closed — returns `sql_cost_unknown_default` (1001.0 by default), which exceeds `sql_max_allowed_cost` (1000.0) by design, so unknown-cost queries are rejected |
| Redis (retrieval cache, run cache) | Any exception, including package missing | Caught, logged at debug level, treated as cache miss/no-op — fail-open |

## Async / Background Processing

- The graph itself runs asynchronously (`async def` node functions), invoked as coroutines by LangGraph.
- `SQLTool.run` and `RetrievalTool.run` are **synchronous** methods, executed via `asyncio.to_thread(...)` from their async node wrappers — this offloads blocking DB/HTTP calls without blocking the event loop.
- `call_agent_llm`'s underlying sync call is further wrapped in a `ThreadPoolExecutor` with `max_workers=1` purely to enforce a hard timeout on an otherwise-blocking LLM SDK call (`future.result(timeout=...)`), and is itself invoked via `asyncio.to_thread` from `decompose_node`/`thought_node`, and directly (synchronously, since `finish_helpers.py` functions are plain `def`) from `finish_node`'s `asyncio.to_thread(answer_subquestion, s)`.
- `trigger_semantic_memory_extraction(...)` and `trigger_episode_write(...)` are called directly (not awaited, not wrapped in `to_thread`) inside `memory_write_node`. Their signatures suggest they may enqueue work rather than perform it inline (naming convention "trigger_..."), but **their implementation is not provided**, so whether they are synchronous, fire-and-forget, or dispatch to Celery/a queue cannot be confirmed from this archive.
- No `celery` import or task decorator appears anywhere in this archive. **Not enough information from the provided code** to document any Celery-based background processing.

## Observability

| Signal | Mechanism | Recorded when | Purpose |
|---|---|---|---|
| Structured node logs | `log_node_event()` (observability/logging.py) | After `decompose`, `sql_tool`, `retrieval_tool`, `finish` nodes complete | Attaches `run_id`, `tenant_id`, `node`, `event`, plus node-specific extras (e.g., `parts=`, `has_data=`) to the log record's `extra["agent"]` |
| Node execution counter | `agent_node_executions_total{node,status}` (Prometheus `Counter`) | In `_run_node`'s `finally` block, for every node it wraps | Tracks success/error counts per node |
| Node duration histogram | `agent_node_duration_seconds{node}` | Same as above | Latency distribution per node, buckets 0.05s–60s |
| SQL rows histogram | `agent_sql_rows_returned` | In `sql_node`, when `result.has_data` | Distribution of row counts returned by SQL queries |
| LLM token counters | `agent_llm_tokens_total{tenant_id,direction}` | Inside `call_agent_llm`, every LLM call | Input/output token consumption per tenant |
| LLM cost counter | `agent_llm_cost_usd_total{tenant_id}` | Inside `call_agent_llm` | Estimated USD cost per tenant, computed from configured per-million-token rates |
| Agent execution counter | `agent_executions_total{tenant_id,status}` | Declared in `metrics.py` | **Declared but not incremented anywhere in this archive** — likely used by a not-provided top-level run wrapper |
| Trace spans | `trace_span()` context manager (observability/tracing.py) | Wraps every `_run_node`-wrapped node | Logs `trace_id` (= `run_id`), `span_id`, `name`, `duration_ms`, `status` on span completion — stdlib-only, not wired to OpenTelemetry/Jaeger in this code, described as "OTEL-compatible shape" only |

Token/cost tracking accumulates on `AgentState` itself (`input_tokens`, `output_tokens`, `llm_cost_usd`, `total_cost`) via `llm_usage_updates()`, so the final state after a run carries the full run's usage totals in addition to the Prometheus counters.

## Security

### Implemented

- **SQL injection / privilege escalation defense:** AST-level validation (`sqlglot`) rejecting non-SELECT statements and forbidden expression types; parameterized tenant predicate (not string concatenation); optional table/column allow-lists.
- **Prompt-injection mitigation:** retrieved documents and SQL results are wrapped with explicit "UNTRUSTED DATA" markers before being placed in LLM prompts; `sanitize_untrusted_block()` regex-filters common injection phrases (e.g., "ignore prior instructions", "you are now", "system prompt:") out of untrusted tool output before it reaches the prompt.
- **Output grounding check:** `validate_answer_grounding` flags (does not block) numeric claims in the final answer that don't appear in the source data, appending a caveat note.
- **Tenant isolation at the SQL layer:** structural, AST-based, as detailed under Multi-Tenancy.
- **Resource limits:** SQL query cost cap (fails closed on unknown cost), row caps, statement timeout (`SET LOCAL statement_timeout`), LLM call timeout, step/sub-question/total-time budgets.

### Not implemented / not visible in the provided code

- Authentication and authorization (JWT, RBAC, session validation) — none of this code validates *who* is making the request; `tenant_id`/`user_id` are accepted as given inputs to `create_initial_state`.
- Input validation/sanitization of the raw user `question` before it reaches the LLM (beyond the SQL/retrieval-output sanitization described above) — no length limits, no profanity/malicious-input filtering visible.
- Encryption-at-rest or in-transit configuration — not this module's concern based on what's shown (would live in DB/Redis client configuration, not provided).
- The regex-based `sanitize_untrusted_block` is a **best-effort filter** covering a fixed, small set of injection phrase patterns; it is not a comprehensive prompt-injection defense and can be bypassed by phrasing not matching those patterns.

> Note: the presence of tenant-predicate injection and output sanitization does not mean the system is broadly "secure" — these are specific, narrow controls; areas without visible controls are called out explicitly above rather than assumed safe.

## Performance

### Implemented Optimizations

- Redis caching of retrieval results and DB schema description, avoiding repeated vector search / schema introspection for repeated questions.
- Circuit breakers preventing repeated slow-failing calls to a degraded LLM or DB dependency.
- SQL cost estimation via `EXPLAIN` before executing a query, rejecting expensive queries pre-emptively (`sql_max_allowed_cost`).
- Row/character/token truncation at multiple layers (`retrieval_doc_preview_chars`, `sql_max_result_rows_in_prompt`, `prompt_max_tokens`, `truncate_to_token_budget`) to bound prompt size and LLM cost/latency.
- SQL/retrieval tool execution offloaded to threads (`asyncio.to_thread`) so the async event loop isn't blocked by synchronous DB/HTTP calls.
- Loop/step/time budgets preventing runaway agent executions.

### Potential Optimization Opportunities

- The `think` LLM call re-runs on every loop iteration even for simple, single-tool questions — no fast-path/heuristic short-circuit before invoking the LLM for routing (the `classify_question_type` heuristic is only used as a forcing function *after* `finish`, not to skip the `think` LLM call outright).
- No caching layer over LLM-generated answers themselves (only over raw retrieval and schema data).
- `agent_executions_total` metric is declared but never incremented, suggesting incomplete instrumentation for run-level (as opposed to node-level) success/failure tracking.
- `run_cache.py`'s idempotency helpers are defined but not invoked, so duplicate-run protection is not currently active in this code path.

## Cost Considerations

LLM calls occur at these points in a single agent run:

```text
Request (one AgentState run)
 ├── decompose            → 1 LLM call (tier="routing")             [every run]
 ├── think                → 1 LLM call per loop iteration            [every sub-question, ≥1x, up to max_steps_per_subquestion]
 ├── sql (sql_generator)  → 1 LLM call (tier="routing")               [conditional: only when routed to "sql"]
 ├── retrieval             → 0 LLM calls (retriever call, not LLM)    [conditional: only when routed to "retrieval"]
 ├── finish (answer_subquestion) → 1 LLM call (tier="generation")    [once per sub-question]
 └── finish (synthesize_final_answer) → 1 LLM call (tier="generation") [only if more than one sub-question]
```

Every LLM call's cost is estimated via `_estimate_cost_usd` using `llm_input_cost_per_million` / `llm_output_cost_per_million` (defaults correspond to Groq's `llama-3.3-70b-versatile` pricing at the time these defaults were set) and accumulated into `AgentState.llm_cost_usd` as well as the Prometheus `agent_llm_cost_usd_total` counter. No actual dollar figures beyond the configured defaults are invented here — real-time pricing should be verified against the current LLM provider rate card.

## Sequence Diagram — Single Sub-Question, Retrieval Path

```mermaid
sequenceDiagram
    participant Caller as Caller (not provided)
    participant Graph as agent_app (LangGraph)
    participant Mem as Memory nodes
    participant Think as think node
    participant LLM as LLMService
    participant Retr as RetrievalTool
    participant RagS as get_retriever (not provided)
    participant Finish as finish node

    Caller->>Graph: invoke(create_initial_state(question, tenant_id, ...))
    Graph->>Mem: memory_read / episodic_recall / semantic_recall
    Mem-->>Graph: conversation_history, episode_context, recalled_memories
    Graph->>Think: decompose (LLM routing call)
    Think->>LLM: call_agent_llm(decompose prompt)
    LLM-->>Think: sub_questions
    Graph->>Think: think (LLM routing call)
    Think->>LLM: call_agent_llm(thought prompt)
    LLM-->>Think: ActionDecision(action="retrieval")
    Graph->>Retr: retrieval_tool.run(state)
    Retr->>Retr: check retrieval cache (Redis)
    Retr->>RagS: get_retriever(tenant_id).invoke(question)  [on cache miss]
    RagS-->>Retr: documents
    Retr-->>Graph: ToolResult(retrieval_context, has_data)
    Graph->>Think: think (re-evaluate; route_action → finish, has data)
    Graph->>Finish: finish node
    Finish->>LLM: call_agent_llm(answer_subquestion prompt, tier="generation")
    LLM-->>Finish: sub_answer_text
    Finish-->>Graph: final_answer (single sub-question)
    Graph->>Mem: memory_write (save turns, trigger semantic/episodic writes)
    Graph-->>Caller: final AgentState
```

## End-to-End Example (Implemented Steps Only)

1. **State creation** — Implemented: `create_initial_state(question, tenant_id, run_id, user_id, session_id)` builds the full initial `AgentState`.
2. **Authentication** — Not implemented / not visible in the provided code.
3. **Memory read** — Implemented: `memory_read` → `episodic_recall` → `semantic_recall` populate `conversation_history`, `episode_context`, `recalled_memories`.
4. **Decomposition** — Implemented: `decompose_node` LLM call sets `sub_questions`.
5. **Agent reasoning loop** — Implemented: `think` → route to `sql_tool` and/or `retrieval_tool` → back to `think`, governed by `route_action` and budget checks, until `finish` is selected.
6. **Tool execution** — Implemented: `SQLTool` (validated, tenant-scoped, cost-checked SELECT) and/or `RetrievalTool` (cached vector retrieval) as selected by the LLM's `ActionDecision`.
7. **Answer generation** — Implemented: `answer_subquestion` assembles bounded context via `WorkingMemory` and calls the generation-tier LLM; output passed through `validate_answer_grounding`.
8. **Synthesis (if multi-part)** — Implemented: `synthesize_final_answer` combines all `sub_answers` into one `final_answer` via another generation-tier LLM call.
9. **Memory write** — Implemented: `memory_write_node` persists the turn and triggers semantic/episodic memory updates (implementation of those triggers not provided).
10. **Metrics/logging** — Implemented: Prometheus counters/histograms and `log_node_event` structured logs recorded throughout via `_run_node`.
11. **Response return** — Not enough information from the provided code — no code shows how `agent_app`'s final state is translated into an HTTP/API response.

## Design Decisions (Inferred)

> The implementation suggests, rather than proves, developer intent in each case below.

- **LangGraph over a hand-rolled loop:** the implementation suggests LangGraph was chosen to get declarative conditional routing (`add_conditional_edges`) and state-merging semantics for free, given the non-trivial branching in `route_action`.
- **Separate `routing` vs `generation` LLM tiers:** the implementation suggests an intent to allow a cheaper/faster model for routing decisions (`decompose`, `think`, SQL generation) versus a stronger model for user-facing answers, via `llm_routing_model` falling back to `llm_generation_model` when unset.
- **Sub-question decomposition:** the implementation suggests this exists to let compound questions get answers gathered independently (with fresh per-question tool state via `per_subquestion_reset`) before a final synthesis pass, rather than trying to gather all evidence for a compound question in one LLM context.
- **Tenant predicate injected via AST rather than trusting the LLM:** the implementation suggests a deliberate defense against prompt-injection or LLM error causing cross-tenant data exposure — the prompt even explicitly tells the LLM not to add its own tenant filter, since the code enforces it structurally regardless of what the LLM outputs.
- **Circuit breakers for both LLM and DB:** the implementation suggests a concern for cascading failures/latency spikes when either external dependency degrades, isolating failures rather than letting every request retry against a down dependency.
- **Fail-open caching (Redis):** the implementation suggests caching is treated as a pure performance optimization, not a correctness dependency — every cache call is wrapped in broad exception handling that degrades to "act as if there was no cache" rather than failing the request.
- **Loop detection heuristics in `route_action`:** the implementation suggests the LLM-driven `think` step is not fully trusted to avoid repeating the same unproductive action indefinitely, so deterministic guardrails were added on top.

## Failure Scenarios

| Failure | Expected Behavior (per code) | Impact |
|---|---|---|
| Redis unavailable | `retrieval_cache.py`/`run_cache.py` catch the exception, log at debug level, return `None`/no-op | Retrieval always misses cache and re-invokes the retriever; run idempotency (if it were wired up) would be disabled; no request failure |
| Vector retriever (`get_retriever`) unavailable/raises | `RetrievalTool.run` catches the exception, returns `ToolResult(observation=f"Error during retrieval: {exc}", has_data=False, retrieval_attempted=True)` | `route_action` treats this as retrieval having been attempted with no results, routing to `finish`; final answer generated with whatever other data (e.g., SQL) is available, or none |
| LLM unavailable/erroring repeatedly | `llm_circuit_breaker` opens after `circuit_breaker_failure_threshold` consecutive failures; subsequent calls immediately raise `RuntimeError` for `circuit_breaker_recovery_seconds` | `thought_node` catches this, forces `finish`, marks `degraded=True`; `decompose_node` falls back to `[question]`; `finish_node`'s own LLM call, if it fails, returns an error message as `final_answer` |
| Database (Postgres) unavailable | `db_circuit_breaker` wraps `SQLValidator.explain_and_execute`; on failure, `SQLTool.run`'s generic `except Exception` catches it, returns an error `ToolResult` with `sql_attempted=True, sql_has_results=False` | `route_action` falls back to `retrieval` if not yet tried, else `finish`; degrades gracefully rather than crashing the run |
| Embedding failure | Not enough information from the provided code — occurs (if at all) inside the not-provided retriever | Not enough information from the provided code |
| Memory backend (`app.memory.*`) failure | No try/except around memory node calls | Exception propagates out of the graph node, failing the entire run — **this is the one component in this archive without a graceful-degradation path** |
| `EXPLAIN` query fails (cost estimation) | `SQLValidator.get_query_cost` catches the exception and fails closed, returning `sql_cost_unknown_default` (1001.0, which exceeds the default `sql_max_allowed_cost` of 1000.0) | The query is rejected as "too expensive" rather than executed blind |

## Testing

No test files (unit or integration) are present in this archive. `agent/eval/harness.py` provides an **offline evaluation harness**, not a test suite in the pytest sense:
- `evaluate_routing_cases()` — runs `classify_question_type` against a golden dataset loaded from `tests/eval/golden_questions.json` (path resolved relative to the repo root; **that JSON file itself is not included in this archive**) and reports pass rate + failure list.
- `evaluate_json_extraction()` — runs `extract_first_json_block` against a list of sample strings and checks the result is well-formed-looking JSON (starts with `{`, ends with `}`).

No mocked dependencies, fixtures, or coverage tooling are visible in this archive.

## Deployment

Not enough information from the provided code — no Dockerfile, docker-compose, process manager config, or startup script is included in this archive. What can be inferred: this module expects to run inside a broader Python application (`app.*` package namespace) with network access to Postgres, an LLM provider, and optionally Redis; and Prometheus metrics are registered at import time via the default `prometheus_client` registry (implying a `/metrics` endpoint is exposed somewhere in the not-provided API layer).

## Known Limitations

### Confirmed Limitations (visible directly in the code)

- Memory node failures (`memory_read`, `semantic_recall`, `episodic_recall`, `memory_write`) are not caught anywhere — an exception in any not-provided memory backend will fail the entire agent run, unlike every other external dependency in this module.
- `agent/utils/token_budget.py`'s `truncate_context`/`estimate_chars` reference `agent_settings.max_prompt_chars`, a field that does **not exist** on `AgentSettings` (which defines `prompt_max_tokens` instead) — calling `truncate_context` with no `max_chars` argument would raise `AttributeError`. This module also does not appear to be imported/used anywhere else in this archive (`context_budget.py`, a similarly-named but distinct module, is what's actually used by `nodes/finish_helpers.py` and `sql_generator.py`).
- `agent_executions_total` (Prometheus counter) is declared in `observability/metrics.py` but never incremented anywhere in this archive.
- `invalidate_schema_cache()` and the run-idempotency cache functions (`get_cached_run_result`/`cache_run_result`) are defined but never called anywhere in this archive.
- The prompt-injection filter (`sanitize_untrusted_block`) matches a fixed, small set of regex patterns and will not catch injection phrasing outside those patterns.
- `validate_answer_grounding`'s numeric-grounding check is a coarse string-matching heuristic (digit sequences) — it can both miss genuinely ungrounded claims (non-numeric hallucinations) and false-flag legitimately-derived numbers (e.g., a percentage computed from source figures that doesn't appear verbatim in the source text).

### Potential Risks / Improvements

- Because SQL generation and tenant-filter injection are decoupled (LLM generates SQL, code injects the filter afterward), any future change to `sql_generator.py` that stops instructing the model to omit `tenant_id` filters, or any SQL shape `sqlglot`'s AST transform doesn't handle (e.g., certain CTEs or subqueries) is a class of correctness risk worth review — this is a "consider reviewing" note, not a demonstrated bug in the current code.
- No explicit authentication/authorization is present in this module; ensuring `tenant_id`/`user_id` on `AgentState` are only ever populated from a verified source is a responsibility that must live entirely in the not-provided caller.
- The `think` step LLM call runs on every loop iteration with no cheaper pre-filter, which could be a latency/cost target for optimization if agent runs commonly need only one tool.

## Future Improvements

Not enough information from the provided code to state the team's actual roadmap; the items under **Potential Optimization Opportunities** and **Potential Risks / Improvements** above are the only improvement-shaped observations supportable by this code.

## Summary

This module is a LangGraph-orchestrated reasoning agent that reads multi-layered memory (conversation/semantic/episodic — implementations external to this archive), decomposes compound questions, iteratively chooses between a tenant-isolated, AST-validated SQL tool and a cached retrieval tool (vector search implementation external to this archive), generates grounded per-sub-question answers with a working-memory-budgeted prompt, optionally synthesizes a combined final answer, and persists the resulting turn back to memory. It layers deliberate resilience (circuit breakers, retries, fail-open caching, loop/budget guards) and observability (Prometheus metrics, structured logs, lightweight trace spans) around every LLM and tool call, with the notable exception that memory-layer failures are not currently caught. Its two clearest security-relevant guarantees are AST-level SQL safety and structural tenant-predicate injection at the database layer; authentication/authorization and comprehensive prompt-injection defense are out of scope for this module as provided.
