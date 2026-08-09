# 🧠 Atlas AI Platform

> A production-grade, multi-tenant AI platform that combines agentic reasoning,
> retrieval-augmented generation, and a three-layer memory system to answer complex
> questions over organizational knowledge.

---

## 📋 Table of Contents

- [The Problem](#the-problem)
- [Why Simpler Approaches Fall Short](#why-simpler-approaches-fall-short)
- [What Atlas AI Is](#what-atlas-ai-is)
- [High-Level Architecture](#high-level-architecture)
- [How It Works: A Request End to End](#how-it-works-a-request-end-to-end)
- [Core Components](#core-components)
- [Agent Architecture Deep Dive](#agent-architecture-deep-dive)
- [RAG Architecture Deep Dive](#rag-architecture-deep-dive)
- [Memory Architecture Deep Dive](#memory-architecture-deep-dive)
- [Memory vs. RAG: Understanding the Distinction](#memory-vs-rag-understanding-the-distinction)
- [Multi-Tenancy](#multi-tenancy)
- [Knowledge Ingestion Flow](#knowledge-ingestion-flow)
- [Why These Components Exist Together](#why-these-components-exist-together)
- [Example: A User Asking a Question](#example-a-user-asking-a-question)
- [Technology Stack](#technology-stack)
- [Repository Structure](#repository-structure)
- [Operational Overview](#operational-overview)
- [Security and Isolation](#security-and-isolation)
- [Observability](#observability)
- [Design Principles](#design-principles)
- [What Makes Atlas AI Architecturally Interesting](#what-makes-atlas-ai-architecturally-interesting)
- [Architecture Map](#architecture-map)
- [Documentation Navigation](#documentation-navigation)

---

## 🔥 The Problem

Organizations accumulate knowledge across many sources: PDF reports, relational databases,
historical records, policies, and conversation history. When someone needs to find an answer,
they face several compounding challenges:

- **Knowledge is scattered.** The information needed to answer a real question rarely lives in
  one place. It may span a document, a database table, and context from a previous conversation.
- **Traditional search is too shallow.** Keyword search finds documents that contain the right
  words, not documents that contain the right answers. The user then has to read, interpret, and
  synthesize those documents themselves.
- **Queries are often complex and multi-step.** A question like *"Compare our Q3 revenue to the
  targets in the planning document, and remind me what we decided last week"* requires database
  access, document retrieval, and memory of a prior conversation — all synthesized into one answer.
- **Context is lost between sessions.** A stateless AI treats every conversation as a fresh start.
  It cannot remember that a user prefers concise bullet points, or that a key term carries a
  domain-specific meaning in this organization.
- **Multiple organizations cannot safely share a system.** In a multi-tenant deployment, Tenant A's
  data must be completely invisible to Tenant B — across documents, conversations, database access,
  and long-term memory.
- **LLM calls are expensive.** Without caching, budget controls, and cost tracking, an AI platform
  can consume enormous compute resources on redundant or runaway queries.

Simple Retrieval-Augmented Generation (RAG) partially addresses the first two problems. But it cannot
handle multi-step reasoning, has no memory of prior interactions, and does not know when to query
a database versus a document store.

Atlas AI is designed to solve all of these problems together.

---

## ⚠️ Why Simpler Approaches Fall Short

A minimal AI system might look like this:

```
User --> Vector Search --> LLM --> Answer
```

This works for simple, isolated questions. It breaks down quickly when:

| Challenge | Why minimal RAG fails |
|---|---|
| Multi-step question | RAG retrieves once and answers. It cannot try a different source if insufficient. |
| Structured data question | RAG searches documents. It cannot query a relational database. |
| Conversational context | RAG has no memory of previous turns. The user must re-explain context every time. |
| Long-running user preferences | The system cannot remember that this user always wants bullet points. |
| Multi-tenant isolation | A simple shared vector store requires careful metadata filtering everywhere, with no architectural enforcement. |
| Cost and performance | A naive pipeline sends every query to the most expensive model with no caching or tracking. |

Atlas AI addresses all of these with an **agentic architecture** that reasons about *how* to answer
before attempting to answer.

---

## 🚀 What Atlas AI Is

Atlas AI is a **multi-tenant AI platform** built for organizations that need to query their own
knowledge — both structured (database tables) and unstructured (documents, PDFs) — using natural language.

At its core, Atlas AI places an **Agent** between the user and the underlying data sources. The Agent
does not blindly retrieve and generate. It thinks: it classifies the question, consults memory,
decides whether the answer requires a document search, a database query, or both, executes those
retrievals, and synthesizes a grounded final answer. After answering, it extracts and persists useful
information for future interactions.

**Who it is for:**
- Organizations that want AI-powered question answering over their own private knowledge and data
- Developers building intelligent assistants on top of proprietary structured and unstructured data
- Teams that need complete tenant isolation — each organization gets its own isolated slice of the system

**What it enables:**
- Answering questions that require reasoning across structured and unstructured data simultaneously
- Conversations that remember context within a session and across sessions
- Per-user and per-tenant knowledge and memory boundaries
- Full observability into AI behavior, costs, and system performance

---

## 🏗️ High-Level Architecture

```
                     +---------------------------+
                     |           User            |
                     +-------------+-------------+
                                   |
                         JWT Auth + Rate Limit
                                   |
                     +-------------v-------------+
                     |       FastAPI              |
                     |       API Layer            |
                     |  (SSE Streaming / REST)    |
                     +-------------+-------------+
                                   |
                     +-------------v-------------+
                     |                           |
                     |  LangGraph Agent Graph    |
                     |                           |
                     +---+----------+--------+---+
                         |          |        |
              +----------v--+  +----v---+  +-v----------+
              | Memory       |  |  RAG   |  | SQL Tool   |
              | System       |  | Tool   |  |            |
              +------+-------+  +---+----+  +-----+------+
                     |              |             |
         +-----------v------+  +----v------+  +---v--------+
         | Short-Term: Redis |  |  Qdrant   |  | PostgreSQL |
         | Episodic: Postgres|  | (Docs +   |  | (Structured|
         | Semantic: Qdrant  |  |  Semantic  |  |  Data)     |
         +-------------------+  |  Memory)  |  +------------+
                                +-----------+
                                   |
                     +-------------v-------------+
                     |   LLM Provider             |
                     |  (Groq / llama-3.3-70b)   |
                     +-------------+-------------+
                                   |
                     +-------------v-------------+
                     |   Final Answer             |
                     |  (streamed via SSE)        |
                     +---------------------------+

  --- Async Background (Celery Workers + Beat) ----------------------
  | Memory extraction after each interaction                         |
  | Episode summary writing after each session turn                  |
  | Document ingestion into the RAG knowledge base                   |
  | Query logging and per-tenant cost tracking                       |
  | Nightly semantic memory pruning                                  |
  -------------------------------------------------------------------

  --- Observability --------------------------------------------------
  | Prometheus metrics + Grafana dashboards                          |
  | MLflow experiment tracking (queries, evaluations, ingestion)     |
  | Sentry error monitoring and ASGI tracing                         |
  -------------------------------------------------------------------
```

---

## ⚙️ How It Works: A Request End to End

Every request flows through the same deliberate sequence. Here is what happens from the moment
a user sends a question to the moment they receive an answer.

### 1. 🔐 Authentication and Rate Limiting
The request arrives at the FastAPI API layer. A JWT token identifies the user and their tenant.
Rate limiting is applied per client IP before any processing begins.

### 2. 💬 Session History Loading
The Agent graph starts executing. Its first node loads the short-term conversation history for the
current session from Redis — the last several turns. This gives the agent immediate conversational
context without loading entire histories.

### 3. 📖 Episodic Recall
The agent loads compact summaries of the user's **previous sessions** from PostgreSQL. These episode
summaries capture what happened in past conversations in compressed form, so the agent has context
across sessions without replaying full history at full cost.

### 4. 🧠 Semantic Memory Recall
The agent queries the user's **semantic memory** in Qdrant: persistent facts, preferences, and tool
hints extracted from previous interactions — filtered strictly to the requesting user and tenant.
If the user mentioned a preferred format or domain-specific context in a prior session, it is recalled here.

### 5. 🔬 Question Decomposition
With all context loaded, the agent sends the question to the LLM for decomposition. Complex questions
are broken into ordered sub-questions. Simple questions pass through as-is. This allows each part
of a complex question to be handled with the right tool.

### 6. 🤔 Reasoning and Tool Selection (Think Node)
For each sub-question, the agent enters a reasoning loop. It classifies the question: does this need
structured data (`data` type → SQL) or document knowledge (`knowledge` type → retrieval)? Based
on what has already been retrieved and this classification, it decides the next action.

### 7. 🔧 Tool Execution

**SQL Tool:** Generates a SQL query, validates it for safety, enforces tenant isolation by injecting
the tenant filter, checks the estimated query cost, and executes it. Results are formatted and
returned to the agent state.

**Retrieval Tool:** Queries the tenant's Qdrant collection using hybrid search (dense + sparse
vectors) with a tenant filter applied. Results are re-ranked and passed back to the agent as
grounded context.

The agent has fallback logic: if SQL returns nothing, it may try retrieval. It actively detects and
breaks out of loops if it begins repeating the same actions.

### 8. ✍️ Answer Synthesis
Once sufficient information is collected, the finish node assembles all context — SQL results,
retrieved document chunks, semantic memories, episodic summaries, and conversation history — into an
LLM prompt. The LLM generates an answer for the current sub-question. If the original question was
decomposed into multiple sub-questions, a second LLM call synthesizes all sub-answers into one
coherent final response.

### 9. 📡 Streaming Response
The final answer is streamed back to the client via **Server-Sent Events (SSE)**. The client
receives real-time events as the agent reasons — thought events, tool-start/end events, and the
final answer — rather than waiting for the entire process to complete silently.

### 10. 💾 Async Memory Persistence
After the answer is returned, the agent writes the new turn to Redis. Two background Celery tasks
are triggered asynchronously:
- **Semantic memory extraction:** The LLM analyzes the completed interaction and extracts durable
  facts, preferences, and tool hints. These are stored in Qdrant.
- **Episode writing:** The session is summarized and stored as an episode in PostgreSQL for future
  cross-session recall.

Neither task blocks the response to the user.

---

## 🧩 Core Components

### 🌐 API Layer

The API layer is a **FastAPI** application that exposes all platform capabilities as REST endpoints.
It handles JWT authentication, request validation, rate limiting, CORS, SSE streaming, and Prometheus
metrics instrumentation.

| Route Prefix | Purpose |
|---|---|
| `/api/auth` | Tenant registration, user login, invitation management, admin approval |
| `/api/agent` | Agentic question answering with SSE streaming |
| `/api/query` | Direct RAG query pipeline (without full agent reasoning) |
| `/api/ingest-rag` | Document ingestion into the knowledge base |
| `/api/memory` | User memory management |
| `/api/internal/metrics` | Internal metrics collection (key-protected) |
| `/api/eval-rag` | RAG evaluation pipeline |
| `/api/recommended-qa` | Tenant-configured recommended Q&A pairs |

> Deep dive: [app/routes/README.md](app/routes/README.md)

### 🤖 Agent

The Agent is the reasoning core of Atlas AI. It is a **LangGraph StateGraph** — a directed graph
where each node performs one specific function and conditional edges determine which node runs next
based on current state. The agent does not apply a fixed pipeline; it reasons dynamically.

> Deep dive: [app/agent/README.md](app/agent/README.md)

### 📚 RAG System

The RAG system provides access to organizational knowledge stored in documents. Documents are
ingested asynchronously, semantically chunked, dual-embedded (dense + sparse), and stored in Qdrant
with tenant metadata. At query time, hybrid search retrieves the most relevant chunks, which are
re-ranked before being presented to the LLM.

> Deep dive: [app/rag/README.md](app/rag/README.md)

### 🧠 Memory System

Three complementary memory layers provide continuity across turns, sessions, and time:
- **Short-Term Memory** — current session conversation history (Redis, TTL-bound)
- **Episodic Memory** — compressed summaries of past sessions (PostgreSQL)
- **Semantic Memory** — durable user facts and preferences (Qdrant, importance-scored)

> Deep dive: [app/memory/README.md](app/memory/README.md)

### ⚡ Background Workers

Non-blocking tasks are dispatched to **Celery** workers with Redis as the broker. Separate queues
handle ingestion, evaluation, and logging. A **Celery Beat** scheduler runs the nightly memory
pruning job.

> Deep dive: [app/celery/README.md](app/celery/README.md)

---

## 🤖 Agent Architecture Deep Dive

The agent is a LangGraph `StateGraph`. Every node reads from and writes to a shared `AgentState`
TypedDict. Conditional edges (`route_action`, `route_after_finish`) determine the execution path at runtime.

```
                 Incoming Request
                        |
             +-----------v-----------+
             |      memory_read      |  Load session turns (Redis)
             +-----------+-----------+
                         |
             +-----------v-----------+
             |    episodic_recall    |  Load cross-session summaries (PostgreSQL)
             +-----------+-----------+
                         |
             +-----------v-----------+
             |    semantic_recall    |  Load user facts (Qdrant)
             +-----------+-----------+
                         |
             +-----------v-----------+
             |       decompose       |  Break question into sub-questions (LLM)
             +-----------+-----------+
                         |
             +-----------v-----------+
             |        think          |  Reason: what action is needed?
             +----+--------+-----+---+
                  |        |     |
         +--------v-+  +---v--+  +-v------+
         | sql_tool |  |retr- |  | finish |
         |          |  |ieval |  |        |
         +--------+-+  +-+----+  +---+----+
                  |      |           |
                  +------+           | (if more sub-questions remain -> back to think)
                     |               |
               back to think         | (if all done)
                                     v
                         +----------+-----------+
                         |     memory_write      |  Persist turn; trigger async tasks
                         +----------------------+
```

**Key agent behaviors:**

| Behavior | How it works |
|---|---|
| Question classification | Before tool selection, each sub-question is classified as `data` (SQL) or `knowledge` (retrieval) |
| Loop detection | Action history is tracked; the agent detects repeated actions and SQL-retrieval oscillation patterns |
| Step budgeting | Each sub-question has a configurable max step count; budget overruns trigger graceful degradation |
| Fallback chaining | SQL failure with no results automatically tries retrieval; both failing causes an early finish |
| Sub-question synthesis | For N sub-questions, a final LLM call synthesizes all N answers into one response |
| Idempotency | Requests with the same `run_id` return the cached result, preventing duplicate LLM costs on retries |
| Prompt injection protection | Retrieved chunks are prefixed with `UNTRUSTED DATA` label to prevent content injection attacks |

> Deep dive: [app/agent/README.md](app/agent/README.md)

---

## 📚 RAG Architecture Deep Dive

RAG operates in two distinct phases: **ingestion** (async, one-time per document) and **retrieval**
(synchronous, per agent request).

### 📥 Ingestion Pipeline

```
Raw Document (PDF, etc.)
         |
         v
  Document Loading (LangChain loaders)
         |
         v
  Token-Based Splitting (2000-token chunks, 50-token overlap)
         |
         v
  Semantic Chunking
  (SemanticChunker refines boundaries by embedding similarity,
   merging or splitting to respect topic coherence)
         |
         v
  Dual Embedding
  (Dense vectors via EmbeddedModel/Jina,
   Sparse vectors via BM25/FastEmbed)
         |
         v
  Storage in Qdrant (tenant_id in payload for isolation)
         |
         v
  File Tracking in PostgreSQL
  (hash-based deduplication -- unchanged files are skipped on re-ingest)
```

### 🔍 Retrieval Pipeline

```
User Query (from Agent)
         |
         v
  In-Process Cache Check (TTLCache, keyed by tenant + query hash)
         |
         v  (cache miss)
  Hybrid Search in Qdrant
  (dense + sparse vectors in one query, filtered by tenant_id)
         |
         v
  Hybrid Re-Ranking (CrossEncoder + BM25 scores combined)
         |
         v
  Top-K Chunks returned to Agent
  (prefixed with UNTRUSTED DATA marker for prompt safety)
```

The hybrid retrieval (dense semantic search + sparse BM25) outperforms dense-only search,
especially for exact-match queries and domain-specific terminology.

> Deep dive: [app/rag/README.md](app/rag/README.md)

---

## 🧠 Memory Architecture Deep Dive

Memory is one of the most architecturally distinctive features of Atlas AI. Three complementary
layers operate at different timescales and serve different purposes.

```
              Atlas AI Memory System
                       |
      +----------------+-----------------+
      |                |                 |
      v                v                 v
Short-Term         Episodic          Semantic
Memory             Memory            Memory
      |                |                 |
Within a session   Across sessions   Durable facts
      |                |                 |
   Redis           PostgreSQL          Qdrant
  (TTL: 2h,       (compressed         (user-scoped,
   20 turns max)   summaries,          importance-scored,
                   90-day retention)   nightly-pruned)
```

### ⚡ Short-Term Memory
- **Stores:** Raw conversation turns (user + assistant) for the active session
- **Read:** First node of every agent run
- **Written:** After the final answer is delivered
- **Why:** Provides immediate conversational context. Redis failures are non-fatal — the answer
  is never blocked by a memory error.

### 📖 Episodic Memory
- **Stores:** LLM-generated compact summaries of completed sessions (not raw turns)
- **Read:** Early in the agent graph, before question decomposition
- **Written:** Asynchronously via Celery after each session turn completes
- **Why:** Allows the agent to know what happened in prior sessions without replaying full histories.

### 💡 Semantic Memory
- **Stores:** Durable user facts, preferences, and tool hints. Types: `fact`, `preference`,
  `tool_hint`. Each carries an importance score (0.0-1.0).
- **Read:** Similarity search against the current question, filtered by `tenant_id` + `user_id`
- **Written:** Asynchronously via Celery. The `MemoryExtractor` uses the LLM to identify what is
  worth retaining. Transient requests, credentials, and chain-of-thought are explicitly excluded.
- **Pruning:** A nightly Celery Beat job removes memories below a configurable importance threshold.

### 🔄 Working Memory (Transient)
A per-request token-budget context assembler: takes all available context (conversation history,
episodic summaries, semantic memories, retrieved documents), sorts by priority, and fits as much
as possible into the configured LLM context window. Destroyed after each request — never persisted.

> Deep dive: [app/memory/README.md](app/memory/README.md)

---

## 🔀 Memory vs. RAG: Understanding the Distinction

Both memory and RAG retrieve information before the LLM generates an answer. They serve fundamentally
different purposes and should not be conflated.

| Dimension | Memory | RAG |
|---|---|---|
| **Purpose** | Remember things about the user and their interactions | Retrieve organizational knowledge from documents |
| **Source** | Prior conversations and LLM-extracted user facts | Ingested documents in the knowledge base |
| **Scope** | Strictly per-user (semantic/episodic/short-term) | Per-tenant (all users share the same knowledge base) |
| **Question answered** | "What do I know about this specific user?" | "What do the organization's documents say about this topic?" |
| **Lifetime** | Permanent (semantic), session-scoped (short-term), recent-sessions (episodic) | Persists as long as documents are in the knowledge base |
| **Written by** | The memory system itself, automatically from interactions | Administrators via document ingestion |
| **Role in prompts** | Personalization and conversational continuity | Factual grounding in organizational knowledge |

The agent uses both simultaneously. It loads user-specific memory before reasoning, and can invoke
the RAG retrieval tool to find relevant document passages. These are complementary, not alternatives.

---

## 🏢 Multi-Tenancy

Atlas AI is designed from the ground up to serve multiple isolated organizations from a single deployment.

```
Platform
|
+-- Tenant A (Organization A)
|   +-- Users (roles: admin / user, with approval workflow)
|   +-- Documents (Qdrant, filtered by tenant_id in payload)
|   +-- Short-Term Memory (Redis key: atlas:stm:{tenant_id}:{user_id}:{session_id})
|   +-- Episodic Memory (PostgreSQL, filtered by tenant_id)
|   +-- Semantic Memory (Qdrant, filtered by tenant_id + user_id)
|   +-- SQL Access (SQLValidator enforces tenant filter on every query)
|
+-- Tenant B (Organization B)
    +-- Users (completely separate from Tenant A)
    +-- Documents (completely separate from Tenant A's)
    +-- Short-Term Memory
    +-- Episodic Memory
    +-- Semantic Memory
```

**Isolation is enforced at multiple independent layers simultaneously:**
- **JWT tokens** carry `tenant_id` and `user_id`; callers cannot override them
- **Qdrant payload filters** are applied on every query for both document retrieval and semantic memory
- **Redis key structure** namespaces all session data by tenant and user
- **PostgreSQL repositories** always include `tenant_id` in queries
- **SQL Tool** (`SQLValidator`) injects the tenant filter into every generated query before execution

**User management:**
- New tenants register with a first admin user
- Additional users join via invitation (configurable approval workflow)
- Admins manage users within their own tenant only
- Rate limiting on registration and login prevents brute-force attacks

---

## 📥 Knowledge Ingestion Flow

Documents enter the system through an asynchronous pipeline that runs entirely off the request path.

```
Administrator uploads document via /api/ingest-rag
         |
         v
  API validates auth and tenant context
         |
         v
  Celery task dispatched to ingest_data_queue
         |
         v
  File hash calculated
  (skip if hash matches a previously processed file)
         |
         v
  Document loaded into text (LangChain loaders)
         |
         v
  Semantic chunking (token split + embedding-based boundary refinement)
         |
         v
  Dual embedding (dense: EmbeddedModel/Jina, sparse: BM25/FastEmbed)
         |
         v
  Stored in Qdrant (tenant_id in payload metadata)
         |
         v
  Processing status tracked in PostgreSQL (processing -> completed / failed)
         |
         v
  Metrics recorded (latency, chunk count, document type)
```

Hash-based deduplication means re-submitting an unchanged document is safe and fast.

---

## 🔗 Why These Components Exist Together

It is worth explaining why Atlas AI cannot be simplified to a basic RAG pipeline.

**User -> RAG -> LLM** handles one class of question: *"What does this document say about topic X?"*

But real organizational questions are rarely that clean:

| Question type | What it needs |
|---|---|
| "What were our Q3 sales?" | SQL tool to query the database |
| "What does the strategy document say about growth?" | RAG retrieval |
| "Compare Q3 sales to the strategy targets" | Both SQL and RAG, synthesized |
| "Based on what we discussed last week, what should I prioritize?" | Episodic memory + possibly retrieval |
| "Remind me -- I prefer concise bullet points" | Semantic memory to recall the preference |
| "Give me a comprehensive analysis" | Question decomposition into sub-questions |

Each component exists because a real class of questions cannot be answered without it:

| Component | Without it, you cannot... |
|---|---|
| Agent | Handle multi-step questions or choose dynamically between SQL and RAG |
| SQL Tool | Answer questions about structured data in the relational database |
| RAG Tool | Answer questions grounded in uploaded documents |
| Short-Term Memory | Maintain a coherent multi-turn conversation |
| Episodic Memory | Remember what happened in previous sessions |
| Semantic Memory | Remember durable user facts and preferences across sessions |
| Celery Workers | Ingest documents or persist memory without blocking API responses |
| Multi-tenancy | Serve multiple organizations safely from one deployment |
| Observability | Know what the system is doing, what it costs, and where it fails |

---

## 💡 Example: A User Asking a Question

**Scenario:** A user in Organization A asks: *"What were the top three revenue drivers last
quarter, and what does the strategy document say about each of them?"*

```
User sends question to /api/agent/ask-agent
         |
         v
JWT validated -> tenant_id and user_id extracted
         |
         v
Agent graph executes:
  |
  +-- memory_read
  |   Loads last N turns from Redis (current session)
  |
  +-- episodic_recall
  |   Loads summaries of last 3 sessions from PostgreSQL
  |
  +-- semantic_recall
  |   Queries Qdrant for user facts matching the question
  |   (e.g., "user prefers concise bullet points")
  |
  +-- decompose
  |   LLM breaks question into two sub-questions:
  |   Sub-Q1: "What were the top three revenue drivers last quarter?"
  |   Sub-Q2: "What does the strategy document say about each driver?"
  |
  +-- think (Sub-Q1) -> classifies as "data" -> routes to sql_tool
  |   sql_tool: generates SQL, validates, enforces tenant filter,
  |             checks query cost, executes, returns structured rows
  |
  +-- finish (Sub-Q1)
  |   LLM generates: "Top 3 drivers: X, Y, Z"
  |
  +-- think (Sub-Q2) -> classifies as "knowledge" -> routes to retrieval_tool
  |   retrieval_tool: hybrid search in Qdrant (tenant-filtered),
  |                   re-ranks results, returns relevant passages
  |
  +-- finish (Sub-Q2)
  |   LLM generates answer grounded in strategy document passages
  |
  +-- synthesize
  |   Single LLM call combines Sub-Q1 and Sub-Q2 answers into one response
  |
  +-- memory_write
      Saves turn to Redis
      Triggers Celery: extract semantic memories
      Triggers Celery: write episode summary
         |
         v
Answer streamed to user via SSE
(user sees thought events and tool events in real time,
 then receives the final synthesized answer)
```

---

## 🛠️ Technology Stack

| Technology | Role in Atlas AI |
|---|---|
| **FastAPI** | API framework: routing, request validation, dependency injection, SSE, Prometheus middleware |
| **LangGraph** | Agent orchestration: stateful graph execution, conditional routing, node lifecycle management |
| **Qdrant** | Vector database: document storage (RAG) and semantic memory — hybrid dense+sparse search |
| **PostgreSQL** | Relational database: user/tenant management, episodic memory, file tracking, cost logs, run records |
| **Redis (Redis Stack)** | Short-term conversation memory, Celery broker and result backend |
| **Celery** | Background task queue: document ingestion, memory extraction, episode writing, query logging |
| **Celery Beat** | Scheduled task dispatcher: nightly semantic memory pruning |
| **LangChain** | Document loading, text splitting, retrieval chain construction |
| **Groq / llama-3.3-70b** | Default LLM provider for agent reasoning and answer generation |
| **Jina AI** | Remote embedding model for document and memory vectors |
| **FastEmbed / BM25** | Sparse vector generation for hybrid retrieval |
| **CrossEncoder (ms-marco-MiniLM)** | Re-ranking model for retrieved document chunks |
| **MLflow** | Experiment tracking: RAG queries, evaluation runs, document ingestion runs |
| **Prometheus** | Metrics collection: HTTP, RAG pipeline, agent nodes, LLM cost, system resources |
| **Grafana** | Metrics visualization (monitoring Docker Compose stack) |
| **Sentry** | Error monitoring and ASGI-level tracing |
| **Alembic** | Database schema migrations |
| **JWT (python-jose)** | Authentication token issuance and validation |
| **Docker / Compose** | Containerized deployment of all services |

---

## 📁 Repository Structure

```
atlas-ai-platform/
|
+-- main.py                        Application entry point, lifespan, middleware, health check
+-- Dockerfile                     Container image definition
+-- docker-compose.yml             Full stack: API, Postgres, Qdrant, Redis, Celery, Beat
+-- docker-compose.monitoring.yml  Prometheus + Grafana monitoring stack
+-- requirements.txt               Python dependencies
+-- alembic/                       Database migration scripts
+-- alembic.ini                    Alembic configuration
+-- logging_config.json            Structured JSON logging configuration
|
+-- app/
|   +-- agent/                     Agent system (LangGraph graph, nodes, tools, prompts)
|   |   +-- core/                  Graph definition, state schema, router, agent config
|   |   +-- nodes/                 All graph node implementations
|   |   +-- tools/                 SQL tool, retrieval tool, tool registry
|   |   +-- prompts/               Prompt registry (decompose, thought, answer synthesis)
|   |   +-- observability/         Agent-specific Prometheus metrics, tracing, logging
|   |   +-- eval/                  Agent evaluation harness
|   |   +-- utils/                 LLM calling, retry, state helpers, classification
|   |
|   +-- rag/                       RAG system (ingestion + retrieval pipelines)
|   |   +-- steps/                 Loader, semantic chunker, embedder, ingest, retriever
|   |   +-- rerankers/             BM25, CrossEncoder, and Hybrid re-ranker
|   |   +-- evaluation/            RAG evaluation pipeline
|   |
|   +-- memory/                    Memory system (all three layers)
|   |   +-- short_term_memory.py   Redis-backed session memory
|   |   +-- episodic_memory.py     PostgreSQL-backed cross-session summaries
|   |   +-- semantic_memory.py     Qdrant-backed durable user facts
|   |   +-- working_memory.py      Per-request token-budget context assembler (transient)
|   |   +-- memory_extractor.py    LLM-based extraction of durable facts from interactions
|   |
|   +-- routes/                    FastAPI route handlers (one file per domain)
|   +-- controllers/               Thin coordination between routes and services
|   +-- services/                  Business logic (auth, memory, RAG services, MLflow, email)
|   +-- repositories/              Database access layer (SQLAlchemy)
|   +-- models/                    SQLAlchemy ORM models (Tenant, User, Episode, CostLog, etc.)
|   +-- schema/                    Pydantic request/response schemas
|   +-- celery/                    Celery app configuration and queue/routing definitions
|   +-- core/                      Shared infrastructure (config, database, Prometheus, rate limiter)
|   +-- design_pattern/            Shared utilities (singleton embedding model)
|
+-- monitoring/
|   +-- prometheus.yml             Prometheus scrape configuration
|   +-- grafana/                   Grafana dashboard definitions
|
+-- tests/                         Test suite
+-- scripts/                       Utility scripts
+-- SRS/                           System Requirements Specification
```

---

## 🚦 Operational Overview

Running Atlas AI requires the following services:

| Service | Purpose | Default Port |
|---|---|---|
| **FastAPI application** | Main API server | 8000 |
| **PostgreSQL 15** | Relational data: users, tenants, episodes, costs | 5432 |
| **Qdrant v1.17** | Vector data: RAG documents and semantic memory | 6333 |
| **Redis Stack 7.2** | Short-term memory, Celery broker and backend | 6379 |
| **Celery Worker** | Background task processing (4 concurrent threads) | — |
| **Celery Beat** | Scheduled task dispatcher (nightly jobs) | — |
| **Prometheus** | Metrics scraping (optional monitoring stack) | 9090 |
| **Grafana** | Metrics dashboards (optional monitoring stack) | 3000 |

**Required environment variables** (application refuses to start without these):

```
API_SECRET_KEY=<long random secret>
POSTGRES_PASS=<database password>
```

**Optional but recommended for production:**

```
GROQ_API_KEY=<LLM provider API key>
JINA_API_KEY=<embedding provider API key>
REDIS_PASSWORD=<Redis auth password>
SENTRY_DSN=<error monitoring DSN>
INTERNAL_METRICS_API_KEY=<protects the /metrics endpoint>
```

**Start all services:**

```bash
cp .env.example .env   # fill in required secrets
docker compose up -d
```

**Start the monitoring stack separately:**

```bash
docker compose -f docker-compose.monitoring.yml up -d
```

Database migrations run automatically on API startup when `RUN_MIGRATIONS=true` is set (the
default in the Docker Compose environment).

---

## 🔒 Security and Isolation

**Authentication:** Every API request requires a JWT bearer token. Tokens are issued at login
and validated on every request. The token payload carries `tenant_id` and `user_id` — callers
cannot override them.

**Authorization:** User roles (`admin`, `user`) control access to tenant management endpoints.
A configurable approval workflow allows new users to require admin approval before they can log in.

**Tenant Isolation:** Enforced at multiple independent layers simultaneously:
- Qdrant payload filters prevent a query for Tenant A from returning Tenant B's documents or memories
- Redis key namespacing (`atlas:stm:{tenant_id}:{user_id}:{session_id}`) prevents cross-user memory access
- PostgreSQL repositories always include `tenant_id` in queries
- The SQL tool's `SQLValidator` injects the tenant filter into every generated query before execution

**Rate Limiting:** Login and registration endpoints are rate-limited per client IP to prevent
brute-force attacks and mass account creation.

**Prompt Injection Protection:** Retrieved document chunks are prefixed with an `UNTRUSTED DATA`
label in the LLM prompt. This prevents malicious content embedded in documents from being
interpreted as system instructions by the LLM.

**Secret Validation at Startup:** The application validates required secrets at import time.
If missing or empty, startup fails immediately with a clear error — preventing accidentally
running production with empty credentials.

**Metrics Endpoint Protection:** The Prometheus `/metrics` endpoint is protected by an
`X-Internal-Key` header in production, preventing external enumeration of tenant IDs, costs,
and system resource usage.

---

## 📊 Observability

AI systems are harder to debug than traditional software. A wrong answer might come from bad
retrieval, a confused agent, an LLM hallucination, or a data quality problem. Atlas AI is
instrumented to surface exactly what happened and why.

**Prometheus Metrics** (collected automatically):
- HTTP request counts, latency histograms, response sizes — by method, endpoint, and status code
- RAG pipeline: vector search duration, chunk count, re-ranking duration, cache hits
- Agent: node execution counts, node durations, SQL rows returned, total executions
- LLM cost: per-tenant cost tracking (input tokens × rate + output tokens × rate)
- System resources: CPU, memory — collected every 10 seconds in the background
- Celery queue depth and task throughput

**MLflow Experiment Tracking:**
- Every RAG query, evaluation run, and document ingestion is logged as an MLflow run
- Experiments: `RAG_Query_Tracking`, `RAG_Evaluation`, `RAG_Data_Ingestion`
- Provides a persistent audit trail of system behavior and model performance over time

**Sentry:**
- ASGI-level error capture with full stack traces and request context
- Configurable trace sampling rate (`SENTRY_TRACES_SAMPLE_RATE`, default 10% in production)

**Structured Logging:**
- All agent nodes, tools, and memory operations emit log events tagged with `tenant_id`,
  `user_id`, and `run_id`
- JSON-formatted logs for compatibility with log aggregation systems

**Health Check:**
- `GET /health` returns application status and version, used by Docker Compose and container
  orchestration for readiness probing

> Deep dive: [app/core/README.md](app/core/README.md)

---

## 📐 Design Principles

These principles are reflected in the actual implementation, not aspirational statements.

**Separation of Responsibilities.**
The Agent reasons and orchestrates. RAG retrieves document knowledge. Memory maintains continuity.
Tools perform actions. Infrastructure stores and moves data. These responsibilities are not
intermingled — each layer has a single well-defined role.

**Tenant Isolation by Default.**
Tenant separation is enforced independently at every storage boundary: Qdrant, Redis, PostgreSQL,
the SQL tool, and JWT authentication all independently enforce isolation. No single point of failure
can cause cross-tenant data leakage.

**Fail Open, Never Block Answers.**
Memory failures (Redis unavailable, Qdrant temporarily unreachable) are logged as warnings but
never propagate to the user as errors. The system degrades gracefully — it answers with less context
rather than refusing to answer. This is explicitly coded in `ShortTermMemory`, `SemanticMemory`,
and `EpisodicMemory`.

**Async by Default for Non-Critical Work.**
Memory persistence, episode writing, query logging, and semantic memory extraction all happen after
the response is delivered, via Celery tasks. User response latency is not impacted by bookkeeping.

**Cost Awareness.**
LLM costs are computed per interaction, persisted in PostgreSQL, and exposed as Prometheus metrics
per tenant. This enables budget monitoring and helps identify expensive query patterns.

**Loop Safety in Agentic Systems.**
The agent graph actively detects repeated actions, oscillating patterns, and step budget overruns.
Rather than looping indefinitely or crashing, it transitions to a degraded-but-functional state and
delivers the best answer it currently has.

**Observability as a First-Class Concern.**
Prometheus metrics, MLflow experiment tracking, Sentry error monitoring, and structured logging are
integrated into the core execution path — not optional extras.

---

## ✨ What Makes Atlas AI Architecturally Interesting

**Three-layer memory with automatic extraction.**
Most AI systems have no persistent memory. Atlas AI has three complementary memory layers operating
at different timescales, and the durable semantic layer is populated automatically by an LLM that
analyzes each completed interaction to identify what is worth remembering long-term.

**Hybrid retrieval with two-stage re-ranking.**
The RAG retrieval combines dense semantic vectors and sparse BM25 keyword vectors in a single Qdrant
query, then applies a hybrid CrossEncoder + BM25 re-ranking pass. This outperforms dense-only
retrieval, especially for exact-match queries and domain-specific terminology.

**Agentic question decomposition.**
Rather than passing the user's question directly to retrieval, the agent first decomposes complex
questions into ordered sub-questions, answers each with the appropriate tool, and synthesizes
the results — making multi-step questions tractable without user intervention.

**Dual-mode data access.**
The agent can answer from both structured relational data (SQL) and unstructured documents (vector
search), and selects between them — or uses both — based on the nature of each sub-question.

**Semantic chunking.**
Documents are first split by token boundaries, then chunk boundaries are refined by semantic
embedding similarity. This produces more coherent retrieval units than fixed-size splitting.

**Prompt injection protection built into retrieval.**
All retrieved document context is labeled `UNTRUSTED DATA` before being placed in the LLM prompt,
a well-established mitigation for prompt injection via malicious document content.

**Idempotent agent runs.**
Requests can include an explicit `run_id`. If the same ID is submitted again on a client retry,
the cached result is returned without re-executing the agent, preventing duplicate LLM costs.

**Nightly memory hygiene.**
A Celery Beat scheduler runs a nightly job to prune low-importance semantic memories, keeping the
memory store focused on genuinely useful information over time.

---

## 🗺️ Architecture Map

| Area | Responsibility | Documentation |
|---|---|---|
| **Agent** | Reasoning, planning, tool selection, question decomposition, answer synthesis | [app/agent/README.md](app/agent/README.md) |
| **RAG** | Document ingestion, semantic chunking, hybrid retrieval, re-ranking | [app/rag/README.md](app/rag/README.md) |
| **Memory** | Short-term, episodic, and semantic memory; extraction and pruning | [app/memory/README.md](app/memory/README.md) |
| **API Routes** | Request routing, authentication, rate limiting, SSE streaming | [app/routes/README.md](app/routes/README.md) |
| **Services** | Auth, invitations, tenant registration, MLflow, email | [app/services/README.md](app/services/README.md) |
| **Data Models** | Tenant, User, Episode, CostLog, TrackedFile ORM schemas | [app/models/README.md](app/models/README.md) |
| **Infrastructure** | Config, database session, Prometheus monitors, rate limiter | [app/core/README.md](app/core/README.md) |
| **Background Workers** | Celery queues, task routing, Beat scheduler | [app/celery/README.md](app/celery/README.md) |
| **Controllers** | Thin coordination layer between routes and services | [app/controllers/README.md](app/controllers/README.md) |

---

## 🔍 Direct RAG Query Pipeline

In addition to the full Agent (`/api/agent/ask-agent`), Atlas AI exposes a **direct RAG query
endpoint** (`/api/query/ask`) that runs the retrieval-generation pipeline without agentic reasoning.

**When to use each:**

| Mode | Endpoint | Use case |
|---|---|---|
| **Agent** | `/api/agent/ask-agent` | Complex, multi-step, or ambiguous questions requiring reasoning and tool selection |
| **Direct RAG** | `/api/query/ask` | Straightforward knowledge questions where retrieval + generation is sufficient |

The direct pipeline still applies all memory layers (short-term, episodic, semantic), caches
results, logs costs, and streams via SSE — it simply skips the graph-based reasoning loop. Both
modes are available simultaneously and are selected by the client per-request.

---

## 🗄️ SQL Engine and Security

The SQL tool inside the Agent is built on a dedicated security layer designed to prevent both data
leakage and destructive operations.

**How a SQL query flows through the engine:**

```
Agent decides SQL is needed
         |
         v
  SQL Generator (LLM-based)
  Generates a natural-language-to-SQL query
         |
         v
  Schema Provider
  Injects the database schema context so the LLM generates valid SQL
         |
         v
  SQLValidator (AST-based, using sqlglot)
  1. Rejects empty or multi-statement queries
  2. Rejects non-SELECT statements (INSERT, UPDATE, DELETE, DROP, ALTER,
     CREATE, TRUNCATE, MERGE, raw Command -- all forbidden)
  3. Injects a parameterized tenant_id WHERE clause
  4. Enforces optional table and column allow-lists
  5. Runs EXPLAIN to estimate query cost before execution
  6. Rejects queries above the configured cost threshold
         |
         v
  Query executed with bound parameters (parameterized, not string-formatted)
         |
         v
  Results capped at max_rows limit
  Returned to Agent state
```

The AST-based validation using `sqlglot` means injected SQL fragments cannot bypass the check
with string tricks — the query is parsed structurally before any execution occurs.

---

## 🧪 Evaluation System

Atlas AI includes a dual evaluation framework — one for the RAG pipeline and one for the Agent
routing logic — so the quality of retrieval and reasoning can be measured systematically.

### RAG Evaluation

The RAG evaluation pipeline (`app/rag/evaluation/`) measures three independent quality dimensions:

| Metric group | What it measures |
|---|---|
| **Retrieval relevance** | Precision, Recall, F1, and MRR — do retrieved chunks match the known-relevant documents? |
| **Retrieval stability** | Jaccard similarity across repeated runs of the same query — is retrieval deterministic? |
| **Rephrase stability** | Jaccard similarity when the same question is rephrased — is retrieval robust to wording variation? |
| **Generation quality** | Token F1 between generated answer and reference answer |

Evaluation runs against a JSON dataset (`evaluation_dataset.json`) containing questions,
relevant document IDs, reference answers, and paraphrases. Results are logged to MLflow under
the `RAG_Evaluation` experiment for historical comparison.

The pipeline is exposed via `/api/eval-rag` and can be triggered on-demand by tenant admins
to measure their knowledge base quality after ingesting new documents.

### Agent Evaluation

The Agent evaluation harness (`app/agent/eval/harness.py`) provides offline testing of:

| Test | What it checks |
|---|---|
| **Routing accuracy** | Does `classify_question_type()` correctly label questions as `data` or `knowledge`? Tested against a golden question set. |
| **JSON extraction** | Does the LLM response parser correctly extract JSON blocks from varied LLM outputs? |

The harness loads golden question cases from `tests/eval/golden_questions.json` and reports
pass rate and failure details — used to catch regressions in classification or parsing logic
before deployment.

---

## 💬 Recommended Q&A

Atlas AI includes a **Recommended Q&A** system that allows tenant administrators to configure
up to 10 pre-defined question-answer pairs for their organization.

**How it works:**
- Pairs are stored in PostgreSQL and loaded into an **in-memory thread-safe cache** at server startup
- When a user asks a question that exactly matches a recommended question, the cached answer is
  returned immediately — no LLM call, no retrieval, zero latency and zero cost
- Admins can add, update, and remove recommended pairs via the `/api/recommended-qa` route
- Changes update the in-memory cache immediately without requiring a server restart

**Why it exists:** Some questions in an organization are asked constantly and have well-known,
stable answers (e.g., "What is our refund policy?"). Caching these at the application level
eliminates repeated RAG and LLM costs for the highest-frequency queries.

---

## 📨 Invitation and User Approval System

User onboarding is controlled through a secure, multi-step invitation workflow.

```
Admin sends invitation
         |
         v
  Invitation token generated (32-byte cryptographically random, 7-day TTL)
  Token stored in PostgreSQL, email sent to invitee
         |
         v
  Invitee clicks link -> registers via /api/auth/register-via-invitation
  Account created with 'pending' or 'approved' status
         |
         v  (if approval required)
  Admin reviews pending users
  Admin approves or rejects -> user notified by email
         |
         v
  Approved users can log in and receive JWT tokens
```

**Key controls:**
- Invitation tokens are time-limited (7 days) and single-use
- Admins can resend expired invitations
- User approval status can be: `approved`, `pending`, `rejected`
- The `approved_by` field records which admin approved the account
- Admins can only manage users within their own tenant

---

## 🚦 Role-Based Rate Limiting

All API endpoints are protected by a **Redis-backed, role-aware rate limiter** that applies
different request budgets based on the authenticated user's role.

| Role | Requests per minute |
|---|---|
| **Admin** | 300 |
| **User** | 100 |
| **Guest / unauthenticated** | 20 |

Authentication-specific endpoints have stricter IP-based limits:

| Endpoint | Limit |
|---|---|
| `/api/auth/login` | 10 attempts / minute / IP |
| `/api/auth/register` | 5 registrations / minute / IP |

Rate limit state is stored in Redis with a 60-second sliding window. Violations are logged for
monitoring and analytics. If Redis is unavailable, rate limiting degrades gracefully rather than
blocking all requests.

---

## 💰 Cost and Run Tracking

Every LLM interaction — whether through the Agent or the direct RAG pipeline — is tracked in
PostgreSQL with full cost attribution.

**Data model:**

```
Runs table (one record per query)
  run_id       UUID primary key
  tenant_id    FK to Tenants (for per-tenant analytics)
  query        The user's question
  answer       The generated response
  latency      End-to-end response time in seconds
  cache_hit    Whether the result came from cache
  retrieved_docs_ids  IDs of retrieved document chunks
  created_at   Timestamp

CostLog table (one-to-many from Runs)
  log_id       UUID primary key
  run_id       FK to Runs (one run can have multiple LLM calls)
  input_tokens   Tokens sent to the LLM
  output_tokens  Tokens generated by the LLM
  model_name     Model used (e.g., llama-3.3-70b-versatile)
  cost_usd       Computed cost (tokens x per-million rate)
  created_at   Timestamp
```

A single agent run may involve multiple LLM calls (e.g., one for decomposition, one per
sub-question, one for synthesis). Each call is recorded as a separate `CostLog` entry linked
to the same run, so total cost per query can be computed by summing all linked entries.

Cost data is also exported as Prometheus metrics (per-tenant) for real-time budget monitoring
in Grafana.

---

## 🛡️ LLM Circuit Breakers

The Agent protects against cascading failures from external LLM and database dependencies using
an **in-process circuit breaker** pattern.

Two circuit breakers are active at all times:

| Breaker | Protects |
|---|---|
| `llm_circuit_breaker` | All LLM API calls (routing and generation) |
| `db_circuit_breaker` | Database queries executed by the SQL tool |

**How it works:**
- After a configurable number of consecutive failures (`circuit_breaker_failure_threshold`, default 5),
  the breaker **opens** and immediately rejects further calls with an error
- After a recovery timeout (`circuit_breaker_recovery_seconds`, default 60s), the breaker enters
  **half-open** state and allows one attempt through
- On success, the breaker **closes** and normal operation resumes
- On failure in half-open state, the breaker opens again for another recovery period

This prevents a failing LLM provider or overloaded database from stalling the entire agent
graph with slow timeouts on every request.

---

## 🛡️ Output Guardrails

Before an agent answer is returned, it passes through **output guardrails** that catch two
categories of problems:

**1. Prompt injection neutralization:**
The guardrail scans retrieved document content for known injection patterns (e.g.,
`"ignore all prior instructions"`, `"you are now"`, `"system prompt:"`) and replaces them
with `[filtered]`. This is a defense-in-depth measure on top of the `UNTRUSTED DATA`
prefix already applied during retrieval.

**2. Numeric grounding validation:**
The guardrail compares numeric values cited in the generated answer against numeric values
present in the retrieved source data. If the answer cites numbers that do not appear in any
retrieved document or SQL result, it appends a note:
> *(Note: some numeric values in this answer could not be verified against retrieved data.)*

This helps surface potential hallucinations without suppressing the answer entirely.

---

## 🗺️ Architecture Map

| Area | Responsibility | Documentation |
|---|---|---|
| **Agent** | Reasoning, planning, tool selection, question decomposition, answer synthesis | [app/agent/README.md](app/agent/README.md) |
| **RAG** | Document ingestion, semantic chunking, hybrid retrieval, re-ranking | [app/rag/README.md](app/rag/README.md) |
| **Memory** | Short-term, episodic, and semantic memory; extraction and pruning | [app/memory/README.md](app/memory/README.md) |
| **API Routes** | Request routing, authentication, rate limiting, SSE streaming | [app/routes/README.md](app/routes/README.md) |
| **Services** | Auth, invitations, tenant registration, MLflow, email, recommended Q&A | [app/services/README.md](app/services/README.md) |
| **Data Models** | Tenant, User, Episode, CostLog, Runs, TrackedFile ORM schemas | [app/models/README.md](app/models/README.md) |
| **Infrastructure** | Config, database session, Prometheus monitors, rate limiter | [app/core/README.md](app/core/README.md) |
| **Background Workers** | Celery queues, task routing, Beat scheduler | [app/celery/README.md](app/celery/README.md) |
| **Controllers** | Thin coordination layer between routes and services | [app/controllers/README.md](app/controllers/README.md) |
| **SQL Engine** | NL-to-SQL generation, AST validation, tenant enforcement, cost estimation | [app/agent/tools/sql_engine/](app/agent/tools/sql_engine/) |
| **Evaluation** | RAG quality metrics + Agent routing evaluation | [app/rag/evaluation/](app/rag/evaluation/) · [app/agent/eval/](app/agent/eval/) |

---

## 🧭 Documentation Navigation

### 🏗️ Architecture
- [High-Level Architecture](#high-level-architecture) — System overview diagram
- [Request Lifecycle](#how-it-works-a-request-end-to-end) — End-to-end request walkthrough
- [Multi-Tenancy](#multi-tenancy) — Isolation model and enforcement points
- [Knowledge Ingestion](#knowledge-ingestion-flow) — How documents enter the system
- [Why Components Exist Together](#why-these-components-exist-together) — Architectural rationale

### 🤖 AI System
- [Agent Architecture](app/agent/README.md) — LangGraph graph, nodes, routing, tools
- [RAG Architecture](app/rag/README.md) — Ingestion pipeline, retrieval, re-ranking
- [Memory Architecture](app/memory/README.md) — All three memory layers, extraction, pruning
- [Memory vs. RAG](#memory-vs-rag-understanding-the-distinction) — Key distinction explained
- [SQL Engine](#-sql-engine-and-security) — NL-to-SQL, AST validation, tenant safety
- [Output Guardrails](#-output-guardrails) — Injection neutralization, grounding validation
- [Circuit Breakers](#-llm-circuit-breakers) — LLM and DB failure protection

### ⚙️ Platform
- [API Reference](app/routes/README.md) — Endpoints, request/response schemas
- [Direct RAG Query Pipeline](#-direct-rag-query-pipeline) — Lightweight query mode
- [Services](app/services/README.md) — Auth, tenant management, MLflow, email
- [Recommended Q&A](#-recommended-qa) — Pre-cached answers for common questions
- [Invitation System](#-invitation-and-user-approval-system) — Onboarding workflow
- [Rate Limiting](#-role-based-rate-limiting) — Role-based and IP-based controls
- [Background Workers](app/celery/README.md) — Task queues, routing, scheduler
- [Infrastructure](app/core/README.md) — Config, database, Prometheus metrics, rate limiting

### 📊 Evaluation and Quality
- [RAG Evaluation](#-evaluation-system) — Precision, Recall, F1, MRR, stability metrics
- [Agent Evaluation](#agent-evaluation) — Routing accuracy and parsing correctness
- [Cost Tracking](#-cost-and-run-tracking) — Per-run, per-call LLM cost attribution

### 🚦 Operations
- [Operational Overview](#-operational-overview) — Required services and configuration
- [Security and Isolation](#-security-and-isolation) — Auth, tenant boundaries, secret management
- [Observability](#-observability) — Prometheus, MLflow, Sentry, structured logging
- [Design Principles](#-design-principles) — Architectural decisions and their rationale

---

*Atlas AI Platform — Version 3.0.0*
