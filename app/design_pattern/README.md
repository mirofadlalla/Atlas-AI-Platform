# Atlas AI — Design Pattern Module (Embedding Singleton, LLM Singleton, Upload Factory)

## Overview

This module is a collection of three loosely related building blocks used elsewhere in Atlas AI, each implementing a classic design pattern:

1. **`embedded_model.py`** — a Singleton `EmbeddedModel` implementing LangChain's `Embeddings` interface, with a three-tier fallback chain (Jina AI → ngrok-hosted vLLM → local SentenceTransformers) and a short-lived exact-match query embedding cache.
2. **`llm_singlton.py`** — a Singleton `LLMService` wrapping the Groq API (`llama-3.3-70b-versatile`) for both blocking and streaming chat completion.
3. **`upload_factory.py`** and **`upload_factory_pattern/`** — two parallel implementations of file/folder ingestion dispatch: a simple imperative function (`upload_factory.py`) and a Factory + Strategy-style implementation (`upload_factory_pattern/`) with a `PathProcessor` interface, `FileProcessor`, `FolderProcessor`, and a `PathProcessorFactory`.

**Provided code:** `embedded_model.py` (208 lines), `llm_singlton.py` (101 lines), `upload_factory.py` (57 lines), `upload_factory_pattern/Interface.py`, `upload_factory_pattern/file_processor.py`, `upload_factory_pattern/folder_processor.py`, `upload_factory_pattern/processor_factory.py`, and a pre-existing `README.md` in the same folder.

**Not provided / Referenced but not provided:** `app.core.config.settings` (the settings object supplying API keys/URLs), `app.controllers.ingest_rag_controller.IngestController` (and its `ingest_file` method), the Qdrant/vector-store consumer of embeddings, and any caller code (routes/services) that instantiates `EmbeddedModel()`, `LLMService()`, `process_upload()`, or `processor_factory`.

> Note: as with the previous module, only the Python source files listed above are treated as verified implementation. Any pre-existing `README.md` content not reflected in the code itself is not used as a source of truth here.

---

## Responsibilities

* Provide a single, process-wide embedding client with automatic multi-provider failover (`EmbeddedModel`).
* Provide a single, process-wide LLM client for Groq-based generation, streaming and non-streaming (`LLMService`).
* Provide a way to ingest either a single file or a directory of files through a common interface, delegating actual ingestion work to `IngestController.ingest_file`.

## Boundaries

* Neither `EmbeddedModel` nor `LLMService` perform retrieval, chunking, prompt construction, or persistence — they are narrow provider-abstraction clients.
* The upload/factory code does not implement file parsing or storage itself — it only walks paths and calls `IngestController.ingest_file` per file, treating that controller as an opaque dependency.
* None of the three components implement authentication, tenant-boundary enforcement, or request routing themselves (tenant_id is accepted and passed through as a plain parameter by the upload code, not derived or validated here).

---

## Project Structure

```
design_pattern/
├── README.md                         # Pre-existing docs (not verified against source)
├── embedded_model.py                 # Singleton embedding client, 3-tier fallback
├── llm_singlton.py                   # Singleton Groq LLM client
├── upload_factory.py                 # Simple imperative file/folder ingest dispatcher
└── upload_factory_pattern/
    ├── Interface.py                  # PathProcessor abstract base class
    ├── file_processor.py             # FileProcessor(PathProcessor)
    ├── folder_processor.py           # FolderProcessor(PathProcessor)
    └── processor_factory.py          # PathProcessorFactory + module-level singleton instance
```

---

## Component 1 — `EmbeddedModel` (`embedded_model.py`)

### Pattern

**Singleton**, implemented via `__new__` with a `threading.Lock()` guarding first construction (double-checked locking), plus a lazy `_ensure_initialized()` guarded by an `_initialized` flag (not thread-locked itself — see Known Limitations).

### Responsibility

Implements LangChain's `Embeddings` interface (`embed_documents`, `embed_query`) so it can be passed directly to LangChain-compatible vector stores/retrievers, while abstracting away which embedding provider actually served the request.

### Fallback Chain

```text
embed_documents(texts) / embed_query(text)
        │
        ▼
 ┌─────────────────────────────┐
 │ Tier 1: Jina AI REST API     │  model: jina-embeddings-v5-text-small
 │ POST https://api.jina.ai/v1/  │  requires settings.jina_api_key
 │ embeddings                    │
 └──────────────┬───────────────┘
                │ on exception → disable jina_enabled for
                │ the remainder of this process's lifetime
                ▼
 ┌─────────────────────────────┐
 │ Tier 2: ngrok-hosted vLLM     │  POST {settings.remote_embed_url}/embed
 │ (fine-tuned model)            │  requires settings.remote_embed_url
 └──────────────┬───────────────┘
                │ on exception → disable remote_enabled for
                │ the remainder of this process's lifetime
                ▼
 ┌─────────────────────────────┐
 │ Tier 3: Local SentenceTrans-  │  BAAI/bge-m3 (cuda if available, else cpu)
 │ formers (always available)    │  falls back to all-MiniLM-L6-v2 on load failure
 └───────────────────────────────┘
```

Important behavior: once Tier 1 or Tier 2 fails **once**, `jina_enabled`/`remote_enabled` are set to `False` for the lifetime of the singleton (i.e., for the life of the process) — the code does not re-attempt a failed tier on subsequent calls. There is no periodic re-probing or reset logic in the provided code.

### Query Embedding Cache

* `_query_embedding_cache`: a class-level `cachetools.TTLCache(maxsize=4096, ttl=60)`, guarded by its own `threading.Lock()`.
* Used only in `embed_query`, keyed on the **stripped, exact text** of the query (`text.strip()`), not a semantic/approximate cache.
* The code comment explains this exists because semantic-memory recall and hybrid document retrieval both request the same dense `retrieval.query` vector during a single `/ask` request — the cache lets the second caller reuse the first's result instead of re-embedding.
* Cached vectors are stored as immutable `tuple`s specifically "so callers cannot mutate the cached vector before Qdrant consumes it," per the inline comment — an explicit defensive-copy design decision.
* `embed_documents` (batch/passage embedding) does **not** use this cache — only single-query embedding does.

### Batching

`embed_documents` splits the input list into chunks of `self.batch_size` (from `EMBED_BATCH_SIZE` env var, default 32) and calls `_embed_batch` per chunk, concatenating results. Each batch independently goes through the full Tier 1→2→3 fallback chain (with tier-disable state shared across batches via the singleton's instance flags).

### Configuration

```env
# read via app.core.config.settings (Referenced but not provided — not visible in this file)
JINA_API_KEY=<your-jina-api-key>          # settings.jina_api_key
REMOTE_EMBED_URL=<your-ngrok-vllm-url>    # settings.remote_embed_url, e.g. https://xxx.ngrok-free.dev

# read directly from environment
EMBED_BATCH_SIZE=32       # default 32
EMBED_TIMEOUT=30          # default 30 (seconds), used for both Jina and ngrok HTTP calls
```

### Error Handling

* Tier 1/2 HTTP failures (`requests` exceptions, `raise_for_status()` errors) are caught with a bare `except Exception`, logged via `logger.exception(...)`, and the tier is disabled for the process; the chain proceeds to the next tier.
* Tier 3 (local model load) has its own inner fallback: `BAAI/bge-m3` load failure is caught and logged, then `all-MiniLM-L6-v2` on CPU is loaded instead. If Tier 3 itself raises (e.g. `sentence-transformers`/`torch` not installed, or the fallback model also fails to load), that exception is **not caught** — it propagates out of `_embed_batch` / `embed_documents` / `embed_query`, since Tier 3 is the last tier and has no further fallback in this file.

---

## Component 2 — `LLMService` (`llm_singlton.py`)

### Pattern

**Singleton** via `__new__`, but **without a locking mechanism** (no `threading.Lock()`), unlike `EmbeddedModel` — see Known Limitations for the resulting race-condition risk under concurrent first-use.

### Responsibility

Wraps the Groq chat completions API for a single hardcoded model, `llama-3.3-70b-versatile`, exposing:

* `generate(...)` — blocking call, returns a dict with `content`, `input_tokens`, `output_tokens`, `total_tokens`.
* `generate_stream(...)` — generator yielding `(content_chunk, None)` for each streamed text delta, and a final `(None, usage_dict)` once Groq's final chunk (via the `x_groq.usage` field) reports token usage.

### Configuration

```env
GROQ_API_KEY=<your-groq-api-key>   # settings.groq_api_key
```

No provider fallback exists here — this is a single-provider client, unlike `EmbeddedModel`'s multi-tier design (the module docstring's "Priority: 1. Groq cloud API (primary)" implies a fallback was planned, but no secondary tier is implemented in the provided code).

### Parameters

`generate` accepts `prompt`, `system_prompt` (default `"You are a helpful assistant."`), `max_new_tokens` (default 2048), `temperature` (default 1.0), and an optional `model` override (defaults to the singleton's fixed model). `generate_stream` accepts the same except no `temperature` or `model` override — temperature is hardcoded to `1` inside the streaming method.

### Error Handling

No try/except appears in either `generate` or `generate_stream` — any Groq API error (auth failure, rate limit, network error) propagates directly to the caller. `Not enough information from the provided code` about retry or fallback behavior at this layer.

---

## Component 3 — Upload / Ingestion Dispatch

Two independent implementations exist in the provided code for the same conceptual task (dispatching file vs. folder uploads to `IngestController.ingest_file`). They are not shown to call each other.

### 3a. `upload_factory.py` — Imperative Version

A single function, `process_upload(file_path, tenant_id, source, author, db)`:

```text
process_upload(path)
    │
    ├─ path does not exist → return {"error": ...}
    ├─ path.is_file() → call IngestController.ingest_file(...) once
    └─ path.is_dir()  → iterate path.iterdir() (non-recursive, top-level only),
                          call IngestController.ingest_file(...) once per file
                          (subdirectories are skipped — only file.is_file() entries)
```

Returns `{"message": f"Processed {N} files", "results": [...]}` where each result contains `file`, `task_id`, and `status` extracted from `IngestController.ingest_file`'s return dict via `.get()`.

### 3b. `upload_factory_pattern/` — Factory + Strategy Version

```text
PathProcessor (Interface.py, ABC)
    │  abstract: can_handle(path) -> bool
    │  abstract: process(path, tenant_id, source, author, db) -> dict
    │
    ├── FileProcessor(PathProcessor)     can_handle: path.is_file()
    │                                    process: single IngestController.ingest_file() call,
    │                                    returns {"type": "file", "file", "path", "task_id",
    │                                             "status", "success"}
    │
    └── FolderProcessor(PathProcessor)   can_handle: path.is_dir()
                                         constructor params: recursive (bool, default False),
                                         file_extensions (list, default None → no filtering)
                                         process: path.rglob("*") if recursive else path.glob("*"),
                                         filtered by _should_process_file (extension match,
                                         case-insensitive, and must be a file),
                                         calls IngestController.ingest_file() per matched file,
                                         returns {"type": "folder", "name", "path", "recursive",
                                                  "files_processed", "results": [...]}

PathProcessorFactory (processor_factory.py)
    │  __init__: self._processors = []; registers FileProcessor() and
    │            FolderProcessor() via _register_default_processors()
    │  register_processor(processor): appends to the ordered processor list
    │  get_processor(path): returns the first processor in the list
    │                       for which can_handle(path) is True, else None
    │  create_folder_processor(recursive, file_extensions): factory method for a
    │                       customized FolderProcessor instance (not auto-registered)
    │
    └── module-level singleton: processor_factory = PathProcessorFactory()
```

`FolderProcessor` here differs from `upload_factory.py`'s folder handling in two ways not present in the simple version: it supports recursive traversal (`path.rglob("*")`) and extension filtering (`file_extensions`).

### Comparison of the Two Implementations

| Aspect | `upload_factory.py` | `upload_factory_pattern/` |
|---|---|---|
| Pattern | Plain function, if/elif branching | Abstract interface + Factory registering concrete strategies |
| Recursive folder traversal | No — `path.iterdir()`, top-level only | Optional, via `FolderProcessor(recursive=True)` |
| Extension filtering | No | Optional, via `file_extensions` param |
| Extensibility | Requires editing the function to add new path types | New path types added by implementing `PathProcessor` and calling `register_processor()` |
| Result shape | `{"message", "results": [{"file","task_id","status"}]}` | Varies by processor: file → flat dict with `success`; folder → nested dict with `files_processed` and per-file `results` |
| Missing-path handling | Explicit check, returns `{"error": ...}` | `Not enough information from the provided code` — `get_processor()` returns `None` if no processor's `can_handle()` matches (e.g. a non-existent path), but no caller code shown handles that `None` case |

`Not enough information from the provided code` as to which of the two implementations is actually wired into a live route/controller, or whether both are in concurrent use, dead code, or one supersedes the other.

---

## External Dependencies

| Dependency | Purpose | Where Used | Required? |
|---|---|---|---|
| `langchain_core.embeddings.Embeddings` | Base interface implemented by `EmbeddedModel` | `embedded_model.py` | Yes |
| `requests` | HTTP calls to Jina AI and ngrok/vLLM endpoints | `embedded_model.py` | Yes |
| `cachetools.TTLCache` | Short-lived exact-match query embedding cache | `embedded_model.py` | Yes |
| Jina AI API | Primary embedding provider | `embedded_model.py` (Tier 1) | Conditionally — only if `jina_api_key` is set |
| ngrok-hosted vLLM endpoint | Secondary embedding provider (fine-tuned model) | `embedded_model.py` (Tier 2) | Conditionally — only if `remote_embed_url` is set |
| `sentence_transformers`, `torch` | Local embedding fallback (BGE-M3 / MiniLM) | `embedded_model.py` (Tier 3) | Yes, as final fallback (imported lazily on first use) |
| `groq` (Groq Python SDK) | LLM chat completions, streaming and non-streaming | `llm_singlton.py` | Yes |
| `app.core.config.settings` | Supplies API keys/URLs (`jina_api_key`, `remote_embed_url`, `groq_api_key`) | `embedded_model.py`, `llm_singlton.py` | Referenced but not provided |
| `app.controllers.ingest_rag_controller.IngestController` | Performs actual file ingestion | `upload_factory.py`, `file_processor.py`, `folder_processor.py` | Referenced but not provided |
| `sqlalchemy.orm.Session` | Passed through to `IngestController.ingest_file` as `db` | `upload_factory.py`, upload_factory_pattern files | Yes (type-only usage; no direct DB queries in this module) |

---

## Configuration

```env
# Embedding provider chain
JINA_API_KEY=<your-jina-api-key>
REMOTE_EMBED_URL=<your-ngrok-or-vllm-endpoint-url>
EMBED_BATCH_SIZE=32
EMBED_TIMEOUT=30

# LLM
GROQ_API_KEY=<your-groq-api-key>
```

`Not enough information from the provided code` regarding the full shape of `app.core.config.settings` (e.g. whether it's a Pydantic `BaseSettings` class) — only the specific attributes referenced (`jina_api_key`, `remote_embed_url`, `groq_api_key`) are visible via usage.

---

## Error Handling

| Component | Failure | Behavior |
|---|---|---|
| `EmbeddedModel` Tier 1 (Jina) | HTTP/API error | Caught, logged (`logger.exception`), tier permanently disabled for this process instance, falls through to Tier 2 |
| `EmbeddedModel` Tier 2 (ngrok vLLM) | HTTP/API error | Caught, logged, tier permanently disabled for this process instance, falls through to Tier 3 |
| `EmbeddedModel` Tier 3 (local) — model load | `BAAI/bge-m3` fails to load | Caught, logged, falls back to `all-MiniLM-L6-v2` on CPU |
| `EmbeddedModel` Tier 3 — total failure | Both local models fail, or `sentence_transformers`/`torch` missing | Not caught — exception propagates to the caller of `embed_documents`/`embed_query` |
| `LLMService.generate` / `generate_stream` | Any Groq API error | Not caught — propagates directly to caller |
| `upload_factory.process_upload` | Path does not exist | Returns `{"error": ...}` instead of raising |
| `upload_factory.process_upload` / processor classes | `IngestController.ingest_file` raises | `Not enough information from the provided code` — no try/except wraps these calls in any of the provided files, so an exception would propagate and likely abort the whole batch (an unhandled exception in one file's ingest call would stop processing of subsequent files in the same loop) |

---

## Observability

* `EmbeddedModel` logs initialization state (`logger.info`) and every tier failure (`logger.exception`), plus a debug log on cache hits (`logger.debug`).
* `LLMService` logs a single `logger.info` line on first construction ("Initializing Groq LLM client...").
* The upload/factory code uses `print()` statements (not the `logging` module) for progress ("📄 Processing file: ...", "📁 Processing folder: ...").
* No metrics, tracing, or cost/token tracking beyond the token counts returned in `LLMService.generate`'s return dict (`input_tokens`, `output_tokens`, `total_tokens`) — these are returned to the caller, not recorded/logged within this module.

---

## Security

* API keys (`jina_api_key`, `groq_api_key`) are read from a settings object rather than hardcoded — no keys are visible in the provided source.
* `tenant_id` is accepted as a plain string parameter throughout the upload/factory code and passed straight through to `IngestController.ingest_file` — this module performs **no validation or enforcement** of tenant boundaries itself; any isolation must happen inside `IngestController`, which is not provided.
* `Not implemented / not visible in the provided code`: input sanitization on `file_path` (e.g. path traversal checks) before being passed to `Path()` and iterated/globbed.

---

## Performance

### Implemented Optimizations
* `EmbeddedModel`'s query embedding TTL cache (60s, exact-match) avoids redundant embedding calls when the same query string is requested twice within a short window by different callers in the same request lifecycle.
* `EmbeddedModel`'s "disable tier after first failure" behavior avoids repeatedly retrying a known-broken provider on every subsequent request within the same process, at the cost of not recovering automatically if that provider becomes healthy again (see Known Limitations).
* `embed_documents` batches texts (`EMBED_BATCH_SIZE`, default 32) to bound request size to each provider.

### Potential Optimization Opportunities
* `EmbeddedModel`'s TTL cache is exact-string-match only; semantically identical but differently-worded queries are not deduplicated.
* Once a tier is disabled it never resets within the process lifetime — a transient Jina outage would degrade all subsequent requests in that process (until restart) to Tier 2/3, even after Jina recovers. This is a potential concern, not a confirmed bug, since no periodic health-check/reset code is required by the design as documented.
* `LLMService.__new__` lacks the locking that `EmbeddedModel.__new__` has, creating a possible (if narrow) race window on first concurrent instantiation from multiple threads.

---

## Failure Scenarios

| Failure | Expected Behavior | Impact |
|---|---|---|
| Jina API unavailable/erroring | Caught, tier disabled, falls to ngrok tier | Embedding still succeeds if Tier 2 or 3 available; increased latency from the failed Tier 1 attempt on every batch until failure is detected once per process |
| ngrok/vLLM endpoint unavailable | Caught, tier disabled, falls to local model | Embedding still succeeds via Tier 3; first local call incurs model load latency |
| Local model load fails (`bge-m3`) | Caught, falls back to `all-MiniLM-L6-v2` | Embedding proceeds with a lower-capacity model |
| Local model load fails entirely (fallback also fails, or dependency missing) | Not caught | Exception propagates out of `embed_documents`/`embed_query` — caller must handle |
| Groq API unavailable/erroring | Not caught | Exception propagates out of `generate`/`generate_stream` — caller must handle |
| Upload path does not exist (`upload_factory.py`) | Explicit check | Returns `{"error": ...}` dict, no exception |
| Upload path does not exist (`processor_factory.get_processor`) | No processor's `can_handle()` returns True | Returns `None`; `Not enough information from the provided code` on caller handling |
| `IngestController.ingest_file` raises mid-batch | Not caught anywhere in this module | Exception propagates, halting the remaining files in that batch/loop |

---

## Testing

No tests were provided in the analyzed code.

---

## Deployment

No Dockerfiles, environment manifests, or startup scripts are included in the provided code. `Not enough information from the provided code` regarding GPU provisioning for the local embedding fallback (`torch.cuda.is_available()` is checked, but no deployment config confirming CUDA availability is provided), or how `REMOTE_EMBED_URL`'s ngrok tunnel is expected to be kept alive/rotated in production.

---

## Known Limitations

### Confirmed Limitations
* `EmbeddedModel._ensure_initialized()` checks `self._initialized` without holding `self._lock` (the lock is only used in `__new__` for instance creation, not for the lazy-init body) — under concurrent first calls to `embed_documents`/`embed_query` from multiple threads, this is a potential (non-fatal, since attributes are simply reassigned) race condition, not something the code explicitly guards against beyond object creation.
* `LLMService.__new__` has no locking at all, unlike `EmbeddedModel` — first concurrent construction across threads is unguarded.
* Once a Jina/ngrok tier fails once, it is disabled for the remainder of the process's life with no retry/reset mechanism in this file.
* `upload_factory.py`'s folder handling is non-recursive and has no extension filtering, unlike the parallel `FolderProcessor` implementation — the two ingestion code paths behave differently for the same input.
* `LLMService` has no fallback provider despite the module docstring implying a "Priority" list — only Groq is implemented.

### Potential Risks / Improvements
* Consider adding a periodic re-probe or manual reset method so a disabled embedding tier can recover without a process restart.
* Consider consolidating `upload_factory.py` and `upload_factory_pattern/` into a single implementation to avoid behavioral drift between the two ingestion paths.
* Consider wrapping `IngestController.ingest_file` calls in per-file try/except within the batch loops so one failing file does not abort processing of the remaining files in the same folder/batch.
* Consider adding the same locking discipline to `LLMService.__new__` that `EmbeddedModel.__new__` already has.

---

## Summary

This module supplies three Singleton/Factory-pattern building blocks for Atlas AI: `EmbeddedModel`, a LangChain-compatible embedding client with an automatic three-tier failover chain (Jina AI → ngrok vLLM → local SentenceTransformers) and a short TTL cache for repeated query embeddings within a request lifecycle; `LLMService`, a single-provider Groq chat-completion client supporting both blocking and streaming generation with token-usage reporting; and two parallel file/folder ingestion dispatchers — a simple imperative function and a Factory + Strategy (`PathProcessor`/`FileProcessor`/`FolderProcessor`/`PathProcessorFactory`) implementation — both of which delegate actual ingestion to an external `IngestController.ingest_file`, which was not included in the provided code.
