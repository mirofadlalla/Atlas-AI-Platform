# 🧠 Atlas AI Platform

> A production-grade, multi-tenant AI platform combining an agentic reasoning engine,
> retrieval-augmented generation (RAG), a three-layer memory system, persistent graph
> checkpoints, and idempotent tool execution — built to answer complex questions over
> organizational knowledge safely and reliably.

**Version:** 3.0.0 · **Stack:** FastAPI · LangGraph · PostgreSQL · Qdrant · Redis · Celery

---

## 📋 Table of Contents

- [What Atlas AI Is](#what-atlas-ai-is)
- [System Architecture](#system-architecture)
- [Request Lifecycle (End-to-End)](#request-lifecycle-end-to-end)
- [Agent Architecture](#agent-architecture)
  - [LangGraph Graph](#langgraph-graph)
  - [Persistent Checkpoints](#persistent-checkpoints)
  - [Tool Idempotency](#tool-idempotency)
  - [Routing & Planning](#routing--planning)
  - [SQL Engine](#sql-engine)
  - [Output Guardrails](#output-guardrails)
  - [Circuit Breakers](#circuit-breakers)
- [RAG Pipeline](#rag-pipeline)
  - [Ingestion](#ingestion)
  - [Retrieval & Re-ranking](#retrieval--re-ranking)
  - [CRAG Relevance Grading](#crag-relevance-grading)
- [Memory System](#memory-system)
- [Multi-Tenancy](#multi-tenancy)
- [API Reference](#api-reference)
- [Background Workers](#background-workers)
- [Observability](#observability)
- [Security](#security)
- [Technology Stack](#technology-stack)
- [Repository Structure](#repository-structure)
- [Getting Started](#getting-started)
- [Configuration Reference](#configuration-reference)

---

## What Atlas AI Is

Atlas AI is a **multi-tenant platform** that lets organizations query their own knowledge — documents, databases, and conversation history — through a single AI interface. It goes beyond simple RAG by:

- **Reasoning** about *how* to answer before answering (agentic planning)
- **Remembering** users across sessions (three-layer memory)
- **Routing** to the right tool — vector search, SQL, or direct LLM — based on query type
- **Recovering** from failures mid-run via persistent graph checkpoints
- **Isolating** every tenant's data at every layer of the system

---

## System Architecture

```mermaid
flowchart TD
    Client["Client / Frontend"]

    subgraph API["FastAPI Application"]
        Routes["Routes\n/agent · /query · /ingest\n/auth · /memory · /admin"]
        Controllers["Controllers\n(Thin coordination layer)"]
        Auth["JWT Auth\n+ Role-based rate limiting"]
    end

    subgraph AgentEngine["Agent Engine (LangGraph)"]
        Router["Fast Hybrid Router\n(regex + LLM classification)"]
        Think["Thought Node\n(ReAct planning)"]
        Decompose["Decompose Node\n(sub-question splitting)"]
        SQLNode["SQL Node\n(NL→SQL + validation)"]
        RetrievalNode["Retrieval Node\n(vector search + CRAG grading)"]
        DirectAnswer["Direct Answer Node"]
        Finish["Finish Node\n(answer synthesis + guardrails)"]
        MemWrite["Memory Write Node"]
        Checkpoint["Persistent Checkpointer\n(SQLite dev / Postgres prod)"]
    end

    subgraph Memory["Three-Layer Memory"]
        STM["Short-Term Memory\n(Redis · session turns)"]
        Episodic["Episodic Memory\n(PostgreSQL · summarised episodes)"]
        Semantic["Semantic Memory\n(Qdrant · long-term facts)"]
    end

    subgraph RAG["RAG Pipeline"]
        Ingest["Ingestion\n(PDF · DOCX · XLSX · PPTX)"]
        Chunk["Semantic Chunker"]
        Embed["Embedding\n(BGE-M3 / Jina)"]
        VectorDB["Qdrant Vector Store\n(per-tenant filtered)"]
        Rerank["Re-ranker\n(BM25 + Cross-Encoder hybrid)"]
    end

    subgraph Infra["Infrastructure"]
        PG["PostgreSQL\n(users · tenants · cost · episodes)"]
        Redis["Redis\n(cache · broker · idempotency locks)"]
        Celery["Celery Workers\n(async ingestion · logging)"]
        Prometheus["Prometheus + Sentry\n(metrics · errors)"]
        MLflow["MLflow\n(experiment tracking)"]
    end

    Client --> Routes
    Routes --> Auth
    Auth --> Controllers
    Controllers --> AgentEngine
    Controllers --> RAG

    AgentEngine --> Memory
    AgentEngine --> Checkpoint
    AgentEngine --> RAG

    SQLNode --> PG
    RetrievalNode --> VectorDB

    Ingest --> Chunk --> Embed --> VectorDB

    Controllers --> Celery
    AgentEngine --> Prometheus
    AgentEngine --> MLflow
    Memory --> STM & Episodic & Semantic
    STM --> Redis
    Episodic --> PG
    Semantic --> VectorDB
```

---

## Request Lifecycle (End-to-End)

```mermaid
sequenceDiagram
    participant U as User
    participant API as FastAPI
    participant Mem as Memory
    participant LG as LangGraph Agent
    participant CP as Checkpoint Store
    participant SQL as SQL Tool
    participant Vec as Vector DB

    U->>API: POST /api/agent/ask-agent {question, session_id}
    API->>API: Validate JWT, enforce rate limit
    API->>Mem: Load fast context (STM + cached semantic)
    API->>CP: Load last checkpoint for thread_id=session_id
    CP-->>LG: Resume from checkpoint (or fresh start)

    LG->>LG: fast_router → classify intent
    alt SQL query
        LG->>SQL: safe_run() — check idempotency cache first
        SQL->>SQL: Generate SQL → Validate → Cost gate → Execute
        SQL-->>LG: ToolResult
    else Document question
        LG->>Vec: safe_run() — check idempotency cache first
        Vec-->>LG: Candidate docs → CRAG relevance grading
    else Direct answer
        LG->>LG: LLM direct response
    end

    LG->>LG: finish_node → synthesise + guardrails
    LG->>CP: Write checkpoint after every node
    LG->>Mem: memory_write_node → persist episode
    LG-->>API: final_answer (streamed SSE)
    API-->>U: Server-Sent Events stream
```

---

## Agent Architecture

### LangGraph Graph

The agent is a **stateful directed graph** compiled by LangGraph. Every node reads from and writes to `AgentState` — a typed dict that carries the full execution context.

```mermaid
flowchart TD
    START([START]) --> FR[fast_router]

    FR -->|direct| DA[direct_answer]
    FR -->|sql| SQL[sql_tool]
    FR -->|retrieval| RET[retrieval_tool]
    FR -->|complex| DC[decompose]

    DA --> MW[memory_write]
    DC --> TH[think]

    SQL -->|SUFFICIENT| FN[finish]
    SQL -->|INSUFFICIENT| TH

    RET -->|SUFFICIENT| FN
    RET -->|INSUFFICIENT| TH

    TH -->|sql| SQL
    TH -->|retrieval| RET
    TH -->|finish| FN

    FN -->|needs more| TH
    FN -->|done| MW

    MW --> END([END])

    style FR fill:#4a90d9,color:#fff
    style TH fill:#7b68ee,color:#fff
    style FN fill:#50c878,color:#fff
    style CP fill:#ff8c00,color:#fff
```

| Node | Role |
|---|---|
| `fast_router` | Regex + LLM hybrid classifier — routes to the right path in <100ms for most queries |
| `direct_answer` | Answers from LLM + memory alone when no tool is needed |
| `decompose` | Splits complex multi-part questions into ordered sub-questions |
| `think` | ReAct planning loop — decides the next tool or finishes |
| `sql_tool` | NL→SQL generation, AST validation, tenant enforcement, execution |
| `retrieval_tool` | Vector search + CRAG relevance grading |
| `finish` | Synthesises all observations into the final answer, applies guardrails |
| `memory_write` | Persists the conversation episode to all three memory layers |

**Key files:**
- [`app/agent/core/graph.py`](app/agent/core/graph.py) — graph definition and compilation
- [`app/agent/core/state.py`](app/agent/core/state.py) — `AgentState` TypedDict
- [`app/agent/nodes/`](app/agent/nodes/) — one file per node

---

### Persistent Checkpoints

> **New in v3.0** — The agent graph now saves state after every node transition.

After every node completes, LangGraph writes a **checkpoint** to a persistent store. If the server crashes or a request times out mid-run, the next call with the same `session_id` resumes exactly where it left off — no work is repeated, no state is lost.

```mermaid
flowchart LR
    A["Node A completes"] --> CP1["Write checkpoint\n(thread_id, node, state)"]
    CP1 --> B["Node B starts"]
    B --> CP2["Write checkpoint"]
    CP2 --> C["Node C starts"]
    C --> CRASH["💥 Crash / timeout"]
    CRASH --> RESUME["Next request:\nLoad checkpoint → Resume at Node C"]
```

| Setting | Dev default | Prod |
|---|---|---|
| Backend | `sqlite` → `./atlas_checkpoints.db` | `postgres` → `lg_checkpoints` table |
| Tables | Managed by `SqliteSaver.setup()` | `lg_checkpoints`, `lg_checkpoint_blobs`, `lg_checkpoint_writes` |
| Thread ID | `session_id` or `run_id` or auto UUID | Same |

**Configure via `.env`:**
```
AGENT_CHECKPOINT_BACKEND=sqlite          # or postgres
AGENT_CHECKPOINT_SQLITE_PATH=./atlas_checkpoints.db
# AGENT_CHECKPOINT_DB_URL=postgresql+psycopg://user:pass@host/db
```

**Key file:** [`app/agent/core/checkpoint.py`](app/agent/core/checkpoint.py)

---

### Tool Idempotency

> **New in v3.0** — Every tool execution is guarded against duplicate runs.

Checkpoints protect against re-running completed *nodes*. Idempotency protects against re-running expensive *tool calls* within a node that is retried.

```mermaid
flowchart TD
    A["tool.safe_run(state)"] --> B{Idempotency\nenabled?}
    B -- No --> RUN["tool.run(state)"]
    B -- Yes --> C{Cache hit?\natlas:idem:{key}}
    C -- Hit --> CACHED["Return cached ToolResult\n✅ No DB / LLM call"]
    C -- Miss --> D{Acquire lock\natlas:lock:{key}}
    D -- Locked --> RUN
    D -- Acquired --> EXEC["tool.run(state)"]
    EXEC --> STORE["Cache result in Redis\n(SQL: 1h · Retrieval: 24h)"]
    STORE --> RELEASE["Release lock"]
    RELEASE --> RETURN["Return ToolResult"]
```

**Key formula:**
```
key = SHA-256( tool_name | tenant_id | run_id | {question, tenant_id, sub_idx} )
```

| Setting | Default |
|---|---|
| `AGENT_TOOL_IDEMPOTENCY_ENABLED` | `true` |
| `AGENT_TOOL_IDEMPOTENCY_SQL_TTL` | `3600` s (1 hour) |
| `AGENT_TOOL_IDEMPOTENCY_RETRIEVAL_TTL` | `86400` s (24 hours) |
| `AGENT_TOOL_IDEMPOTENCY_LOCK_TTL` | `30` s |

**Key files:**
- [`app/agent/tools/idempotency.py`](app/agent/tools/idempotency.py) — key building, Redis lock/cache helpers
- [`app/agent/tools/base.py`](app/agent/tools/base.py) — `AgentTool.safe_run()` guard

---

### Routing & Planning

**Fast Hybrid Router** (`fast_router` node):

1. **Regex pass** — 30+ patterns detect obvious intents (SQL keywords, greeting phrases) in <1ms
2. **LLM classification** — for ambiguous queries, a lightweight model classifies into: `sql`, `retrieval`, `direct`, `decompose`
3. **Memory flag setting** — simultaneously decides which memory layers to load (`needs_short_term`, `needs_semantic`, `needs_episodic`)

**ReAct Planning** (`think` node):

The thought node runs a Reason-Act loop. Each iteration produces a structured output:
```
Thought: I need to look up X in the database.
Action: sql
```
The loop continues until the agent decides it has enough to answer, or hits `max_steps_per_subquestion` (default: 6).

---

### SQL Engine

The SQL engine is a multi-stage safety pipeline:

```mermaid
flowchart LR
    Q["Natural language\nquestion"] --> GEN["SQL Generator\n(LLM + schema context)"]
    GEN --> VAL["AST Validator\n(sqlglot parsing)"]
    VAL --> TEN["Tenant Enforcer\n(inject tenant_id filter)"]
    TEN --> COST["Cost Gate\n(EXPLAIN → reject if > limit)"]
    COST --> EXEC["Execute\n(SET LOCAL statement_timeout)"]
    EXEC --> FMT["Format results\n(max 1000 rows)"]
```

| Stage | Protection |
|---|---|
| AST Validation | Blocks non-SELECT statements (INSERT/UPDATE/DROP) |
| Tenant Enforcement | Injects `WHERE tenant_id = ?` on all queries |
| Allowed Tables/Columns | Optional allowlist from `AGENT_SQL_NAMESPACE` |
| Cost Gate | EXPLAIN plan cost must be < `AGENT_SQL_MAX_ALLOWED_COST` |
| Statement Timeout | `SET LOCAL statement_timeout = Ns` per connection |

**Key files:** [`app/agent/tools/sql_engine/`](app/agent/tools/sql_engine/)

---

### Output Guardrails

Two protection layers applied to every agent answer:

**Layer 1 — Prompt Injection Sanitization** (`sanitize_untrusted_block`)
Applied to retrieved documents before they reach the LLM. Neutralizes 25+ injection patterns:
- `ignore previous instructions` / `forget all above`
- Role-switching: `you are now`, `act as`, `pretend to be`
- Delimiter injection: `[INST]`, `<|im_start|>`, ChatML tokens
- Jailbreaks: `DAN`, `developer mode`, `no restrictions`

**Layer 2 — Numeric Grounding Validation** (`validate_answer_grounding`)
Compares numbers in the generated answer against numbers in the source data. If the LLM cites a value that does not appear in any retrieved document or SQL result, the answer is annotated:
> *(Note: some numeric values in this answer could not be verified against retrieved data.)*

**Key file:** [`app/agent/utils/guardrails.py`](app/agent/utils/guardrails.py)

---

### Circuit Breakers

In-process circuit breakers protect against cascading failures:

```
CLOSED (normal) → 5 consecutive failures → OPEN (reject immediately)
OPEN → after 60s recovery timeout → HALF-OPEN (try one request)
HALF-OPEN → success → CLOSED | failure → OPEN
```

Separate breakers exist for: **LLM calls**, **SQL execution**, **vector retrieval**. When open, the agent degrades gracefully — it marks `degraded=True` and returns a partial answer rather than hanging.

**Key file:** [`app/agent/utils/circuit_breaker.py`](app/agent/utils/circuit_breaker.py)

---

## RAG Pipeline

### Ingestion

```mermaid
flowchart LR
    UP["Upload\n(file or folder)"] --> DET["Structure Detector\n(PDF/DOCX/XLSX/PPTX)"]
    DET --> LOAD["Loader\n(per-format parser)"]
    LOAD --> CHUNK["Semantic Chunker\n(sentence boundary aware)"]
    CHUNK --> EMBED["Embedding\n(BGE-M3 local / Jina API)"]
    EMBED --> TRACK["File Tracker\n(dedup via hash)"]
    TRACK --> QDRANT["Qdrant\n(tenant-namespaced collection)"]
```

- **Supported formats:** PDF, DOCX, XLSX, PPTX, plain text
- **Chunking:** semantic boundary-aware (not fixed-size) — preserves sentence and paragraph integrity
- **Deduplication:** SHA-256 hash of each file; already-indexed files are skipped
- **Embedding providers:** `bge` (local BGE-M3, default in production), `jina` (API, default in dev), `auto` (falls back)
- **Async ingestion:** large uploads are offloaded to Celery workers

### Retrieval & Re-ranking

```mermaid
flowchart LR
    Q["Question"] --> VEC["Qdrant similarity search\n(top-k=5, tenant filter)"]
    VEC --> PRE["Score pre-filter\n(retrieval_score_floor)"]
    PRE --> RERANK["Hybrid Re-ranker"]
    RERANK --> BM25["BM25 lexical scoring"]
    RERANK --> CE["Cross-Encoder\n(semantic re-scoring)"]
    BM25 & CE --> MERGE["Score fusion\n(weighted combination)"]
    MERGE --> GRADE["CRAG Relevance Grader"]
```

**Re-ranker options** (set via `RERANKER_PROVIDER`):
- `local` — sentence-transformers cross-encoder (no API key needed)
- `jina` — Jina Reranker v3.5 API
- BM25 is always applied alongside whichever semantic re-ranker is active

### CRAG Relevance Grading

After retrieval and re-ranking, a lightweight LLM grades each candidate chunk against the query. Chunks that fail the relevance threshold are discarded before the LLM sees them. This means:
- The LLM context is never polluted with irrelevant content
- If 0 chunks survive grading, the agent falls back to SQL or marks retrieval as insufficient

**Key files:** [`app/rag/`](app/rag/), [`app/agent/core/relevance_grader.py`](app/agent/core/relevance_grader.py)

---

## Memory System

The platform maintains three independent memory layers per user:

```mermaid
flowchart LR
    subgraph STM["Short-Term Memory\n(Redis · TTL: 2h · max 20 turns)"]
        S1["Turn 1"]
        S2["Turn 2"]
        S3["..."]
    end

    subgraph EP["Episodic Memory\n(PostgreSQL · summarised)"]
        E1["Session summary 1"]
        E2["Session summary 2"]
    end

    subgraph SEM["Semantic Memory\n(Qdrant · long-term facts)"]
        F1["User prefers bullet points"]
        F2["Key domain term: X means Y"]
    end

    NEW["New turn"] --> STM
    STM -->|session ends| EXTRACT["Memory Extractor\n(LLM extracts facts + summary)"]
    EXTRACT --> EP
    EXTRACT --> SEM
```

| Layer | Storage | Purpose | TTL |
|---|---|---|---|
| **Short-Term** | Redis | Recent conversation turns (verbatim) | 2 hours / 20 turns |
| **Episodic** | PostgreSQL | Compressed summaries of past sessions | Permanent (prunable) |
| **Semantic** | Qdrant | Long-term user facts, preferences, domain knowledge | Permanent |

**Memory loading** is parallelised at request time:
- Short-term is always loaded (fast Redis GET)
- Semantic + episodic are loaded from cache on first request, then from DB on subsequent requests in the same session

**Key files:** [`app/memory/`](app/memory/)

---

## Multi-Tenancy

Every layer of the system enforces tenant isolation:

| Layer | Isolation mechanism |
|---|---|
| **Authentication** | JWT contains `tenant_id`; never trusted from request body |
| **PostgreSQL** | All tables have `tenant_id` column; queries always filter by it |
| **Qdrant** | Tenant-specific metadata filter on every vector search |
| **SQL Tool** | `WHERE tenant_id = ?` injected into every generated query via AST rewrite |
| **Redis** | All cache keys are prefixed with `tenant_id` |
| **Tenant Databases** | Optional: each tenant can connect their own external database (MySQL or PostgreSQL) with encrypted credentials |

Tenant databases are registered via the admin API and accessed through a connection pool managed by `TenantDatabaseService`. Credentials are encrypted at rest using `CREDENTIAL_ENCRYPTION_KEY`.

---

## API Reference

All endpoints are under `/api`. Authentication required (JWT Bearer) unless noted.

| Method | Path | Description |
|---|---|---|
| `POST` | `/agent/ask-agent` | Streaming SSE agent response |
| `POST` | `/agent/ask-agent-batch` | Non-streaming agent response |
| `POST` | `/query/ask` | Lightweight direct RAG query (no agent) |
| `POST` | `/ingest-rag/upload-file` | Upload a file for indexing |
| `POST` | `/ingest-rag/upload-folder` | Upload a folder for indexing |
| `GET` | `/ingest-rag/tracked-files` | List indexed files for tenant |
| `DELETE` | `/ingest-rag/delete-file/{id}` | Remove a file from the index |
| `GET` | `/memory/episodes` | List episodic memory for user |
| `DELETE` | `/memory/episodes/{id}` | Delete a memory episode |
| `GET` | `/recommended-qa` | Get pre-cached Q&A pairs |
| `POST` | `/auth/register` | Register a new user |
| `POST` | `/auth/login` | Obtain JWT token |
| `POST` | `/auth/invite` | Send invitation email |
| `POST` | `/tenant-database/connect` | Register a tenant's external DB |
| `GET` | `/health` | Health check (no auth) |
| `GET` | `/metrics` | Prometheus metrics (internal key) |
| `POST` | `/super-admin/setup` | Bootstrap first super-admin (one-time) |

**Agent request body:**
```json
{
  "question": "What was our Q3 revenue?",
  "session_id": "user-session-abc123",
  "run_id": "optional-idempotency-key"
}
```

**SSE event types (streaming):**
```
tool_start  — node begins execution
thought     — word-by-word reasoning stream
tool_end    — node completed
answer      — word-by-word answer stream
complete    — full answer + metadata
done        — run finished
error       — recoverable error
```

---

## Background Workers

Celery handles all async and periodic work:

```mermaid
flowchart LR
    API["FastAPI"] -->|enqueue| BROKER["Redis Broker"]
    BROKER --> WORKER["Celery Worker\n(concurrency: 2)"]
    BEAT["Celery Beat\n(scheduler)"] --> BROKER

    WORKER --> L1["Agent run logging\n(cost, tokens, latency)"]
    WORKER --> L2["RAG query logging"]
    WORKER --> L3["File ingestion\n(large uploads)"]
    BEAT --> L4["Periodic memory pruning"]
    BEAT --> L5["Recommended Q&A refresh"]
```

- **Broker:** Redis DB 0
- **Result backend:** Redis DB 1
- **Worker concurrency:** 2 (configurable)
- **Beat scheduler:** periodic tasks (memory pruning, cache refresh)

**Key file:** [`app/celery/celery_config.py`](app/celery/celery_config.py)

---

## Observability

| System | What it covers |
|---|---|
| **Prometheus** | Node execution count + duration, SQL rows returned, agent run count, HTTP request rate/latency/size, resource metrics (CPU, memory) |
| **MLflow** | RAG evaluation experiments, retrieval quality metrics (Precision, Recall, F1, MRR, NDCG), retrieval stability |
| **Sentry** | Unhandled exceptions, slow transaction traces (`SENTRY_TRACES_SAMPLE_RATE=0.1` default) |
| **Structured logging** | JSON log output via `python-json-logger`; every node logs `run_id`, `tenant_id`, event type, and outcome |
| **Cost tracking** | Per-run LLM cost (input + output tokens × price per million), SQL query cost (EXPLAIN estimate), stored in `cost_log` table |

**Prometheus metrics exposed at** `/metrics` (protected by `X-Internal-Key` header):

```
agent_node_executions_total{node, status}
agent_node_duration_seconds{node}
agent_sql_rows_returned
agent_executions_total{tenant_id, status}
http_requests_total{method, endpoint, status_code}
http_request_duration_seconds{method, endpoint}
```

---

## Security

| Concern | Implementation |
|---|---|
| **Authentication** | JWT (HS256), validated on every request via `get_current_user` dependency |
| **Role-based access** | Roles: `user`, `admin`, `super_admin`; enforced per-route |
| **Rate limiting** | Per-role and per-IP sliding window (in-memory + Redis) |
| **SQL injection** | AST-level validation via `sqlglot`; parameterised queries only |
| **Prompt injection** | 25+ regex patterns strip injection phrases from retrieved content before LLM sees it |
| **Tenant isolation** | `tenant_id` from JWT, never from request body; injected into every DB/vector query |
| **Credential encryption** | External tenant DB credentials encrypted with Fernet (`CREDENTIAL_ENCRYPTION_KEY`) |
| **Secret management** | Required secrets fail-fast at startup if unset (`POSTGRES_PASS`, `API_SECRET_KEY`) |
| **CORS** | Configurable `ALLOW_ORIGINS`; defaults to `http://localhost:3000` |

---

## Technology Stack

| Category | Technology |
|---|---|
| **API framework** | FastAPI 0.115 + Uvicorn |
| **Agent graph** | LangGraph 1.0 (stateful graph with persistent checkpoints) |
| **LLM** | OpenAI-compatible API (routing: `gpt-oss-20b`, generation: `gpt-oss-120b`) + Groq fallback |
| **Vector database** | Qdrant 1.17 |
| **Relational database** | PostgreSQL 15 (SQLAlchemy 2.0 ORM, Alembic migrations) |
| **Cache / broker** | Redis Stack 7.2 |
| **Task queue** | Celery 5.3 (worker + beat) |
| **Embeddings** | BGE-M3 (local, via sentence-transformers) · Jina AI API |
| **Re-ranking** | BM25 + Cross-Encoder hybrid · Jina Reranker v3.5 |
| **Checkpoint storage** | SQLite (dev) · PostgreSQL via psycopg3 (prod) |
| **Idempotency store** | Redis (`SETNX` lock + `SETEX` result cache) |
| **Observability** | Prometheus · MLflow · Sentry · python-json-logger |
| **Schema migrations** | Alembic |
| **Containerisation** | Docker + Docker Compose |

---

## Repository Structure

```
Atlas-AI-Platform/
│
├── main.py                        # FastAPI app entry point, lifespan hooks
├── requirements.txt               # Pinned dependencies
├── docker-compose.yml             # Full stack: API + Celery + PG + Qdrant + Redis
├── Dockerfile
├── alembic/                       # Database migration scripts
│   └── versions/
│       ├── 20260001_add_langgraph_checkpoints.py
│       └── 20260002_add_tool_idempotency_log.py
│
└── app/
    ├── agent/                     # 🤖 Agent engine
    │   ├── core/
    │   │   ├── graph.py           # LangGraph graph definition
    │   │   ├── state.py           # AgentState TypedDict
    │   │   ├── checkpoint.py      # Persistent checkpointer factory (NEW)
    │   │   ├── config.py          # AgentSettings (env-driven)
    │   │   ├── router.py          # Routing logic and edge conditions
    │   │   └── relevance_grader.py# CRAG LLM grading
    │   ├── nodes/                 # One file per graph node
    │   │   ├── sql_node.py
    │   │   ├── retrieval_node.py
    │   │   ├── thought_node.py
    │   │   ├── finish_node.py
    │   │   ├── decompose_node.py
    │   │   ├── direct_answer_node.py
    │   │   └── memory_nodes.py
    │   ├── tools/
    │   │   ├── base.py            # AgentTool ABC + safe_run() (NEW)
    │   │   ├── idempotency.py     # Redis lock/cache helpers (NEW)
    │   │   ├── sql_tool.py        # NL→SQL execution
    │   │   ├── retrieval_tool.py  # Vector search
    │   │   ├── retrieval_cache.py # Redis retrieval cache
    │   │   └── sql_engine/        # SQL generation + AST validation
    │   ├── utils/
    │   │   ├── guardrails.py      # Prompt injection + grounding checks
    │   │   ├── circuit_breaker.py # LLM/DB circuit breakers
    │   │   ├── context_budget.py  # Token budget enforcement
    │   │   ├── run_cache.py       # Run-level result caching
    │   │   └── state_helpers.py   # State manipulation utilities
    │   ├── prompts/               # Prompt registry
    │   ├── observability/         # Node-level logging, metrics, tracing
    │   └── eval/                  # Agent routing evaluation harness
    │
    ├── rag/                       # 📄 RAG pipeline
    │   ├── ingest_data_pipline.py
    │   ├── retrivel_data_pipline.py
    │   ├── reranker.py
    │   ├── rerankers/             # BM25, cross-encoder, hybrid, Jina
    │   ├── steps/                 # Loader, chunker, embedder, tracker
    │   └── evaluation/            # RAG quality metrics (MLflow)
    │
    ├── memory/                    # 🧠 Memory system
    │   ├── memory_manager.py      # Unified interface (load/write)
    │   ├── short_term_memory.py   # Redis-backed turns
    │   ├── episodic_memory.py     # PostgreSQL-backed summaries
    │   ├── semantic_memory.py     # Qdrant-backed long-term facts
    │   ├── memory_extractor.py    # LLM fact extraction
    │   └── summarizer.py          # Session summarisation
    │
    ├── routes/                    # 🌐 FastAPI routers
    ├── controllers/               # Coordination layer
    ├── services/                  # Business logic
    │   ├── auth_services/
    │   ├── rag_services/
    │   ├── tenant_database_service.py
    │   ├── invitation_service.py
    │   └── mlflow_service.py
    ├── models/                    # SQLAlchemy ORM models
    ├── repositories/              # DB access layer
    ├── schema/                    # Pydantic request/response schemas
    ├── core/                      # Config, DB session, rate limiter, Prometheus
    ├── design_pattern/            # Singleton (LLM, Embedding), Factory (upload)
    └── celery/                    # Celery app configuration
```

---

## Getting Started

### Prerequisites
- Docker + Docker Compose
- OpenAI-compatible API key (or Groq key)
- Jina API key (optional, for dev embedding)

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — required fields:
# API_SECRET_KEY, POSTGRES_PASSWORD, REDIS_PASSWORD
# GROQ_API_KEY or OPENAI-compatible endpoint
```

### 2. Start all services

```bash
docker compose up -d
```

This starts: **PostgreSQL** · **Qdrant** · **Redis** · **FastAPI** · **Celery Worker** · **Celery Beat**

Alembic migrations run automatically on API startup (`RUN_MIGRATIONS=true`).

### 3. Create the first super-admin

```bash
curl -X POST http://localhost:8000/api/super-admin/setup \
  -H "Content-Type: application/json" \
  -d '{"secret_key": "<SUPER_ADMIN_SECRET_KEY>", "email": "admin@org.com", "password": "..."}'
```

### 4. Ingest documents

```bash
# Get a JWT first
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -d '{"email":"admin@org.com","password":"..."}' | jq -r .access_token)

# Upload a file
curl -X POST http://localhost:8000/api/ingest-rag/upload-file \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@report.pdf"
```

### 5. Ask a question

```bash
curl -X POST http://localhost:8000/api/agent/ask-agent-batch \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "Summarise the key findings from the report", "session_id": "my-session"}'
```

### Running tests

```bash
pytest tests/ -v
```

---

## Configuration Reference

All settings use environment variables. Agent-specific settings are prefixed `AGENT_`.

### Core

| Variable | Default | Description |
|---|---|---|
| `API_SECRET_KEY` | **required** | JWT signing key |
| `POSTGRES_PASS` | **required** | PostgreSQL password |
| `POSTGRES_HOST` | `localhost` | PostgreSQL host |
| `POSTGRES_DB` | `""` | Database name |
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PASSWORD` | — | Redis auth password |
| `ENVIRONMENT` | `development` | `development` or `production` |
| `EMBEDDING_PROVIDER` | `jina` | `jina`, `bge`, or `auto` |

### Agent

| Variable | Default | Description |
|---|---|---|
| `AGENT_CHECKPOINT_BACKEND` | `sqlite` | `sqlite` (dev) or `postgres` (prod) |
| `AGENT_CHECKPOINT_SQLITE_PATH` | `./atlas_checkpoints.db` | SQLite file path |
| `AGENT_CHECKPOINT_DB_URL` | _(derived)_ | Explicit psycopg3 URL for Postgres checkpointer |
| `AGENT_TOOL_IDEMPOTENCY_ENABLED` | `true` | Enable/disable tool idempotency guard |
| `AGENT_TOOL_IDEMPOTENCY_SQL_TTL` | `3600` | SQL result cache TTL (seconds) |
| `AGENT_TOOL_IDEMPOTENCY_RETRIEVAL_TTL` | `86400` | Retrieval result cache TTL (seconds) |
| `AGENT_TOOL_IDEMPOTENCY_LOCK_TTL` | `30` | In-flight lock expiry (seconds) |
| `AGENT_MAX_STEPS_PER_SUBQUESTION` | `6` | ReAct loop steps per sub-question |
| `AGENT_MAX_TOTAL_STEPS` | `50` | Hard cap on total graph steps |
| `AGENT_SQL_QUERY_TIMEOUT_SECONDS` | `30` | SQL execution timeout |
| `AGENT_RETRIEVAL_TIMEOUT_SECONDS` | `30` | Vector retrieval timeout |
| `AGENT_SQL_MAX_ALLOWED_COST` | `1000` | EXPLAIN cost threshold |
| `AGENT_LLM_ROUTING_MODEL` | `openai/gpt-oss-20b` | Fast routing model |
| `AGENT_LLM_GENERATION_MODEL` | `openai/gpt-oss-120b` | Synthesis model |
| `AGENT_CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | Failures before circuit opens |
| `AGENT_RETRIEVAL_GRADING_ENABLED` | `true` | Enable CRAG LLM grading |

### Observability

| Variable | Default | Description |
|---|---|---|
| `SENTRY_DSN` | — | Sentry project DSN |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.1` | Trace sampling rate (0–1) |
| `INTERNAL_METRICS_API_KEY` | — | Key for `/metrics` endpoint |

---

*Atlas AI Platform — Version 3.0.0*
