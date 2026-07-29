# Atlas AI Agent

LangGraph ReAct-style agent: **decompose → think → sql / retrieval → finish**.

## Architecture

```
User question
    ↓
decompose   (split compound questions)
    ↓
think       (LLM chooses sql | retrieval | finish)
    ↓
router      (loop guard, fallbacks, force-tool rules)
    ↓
sql_tool | retrieval_tool | finish
    ↓
(loop until finish, then next sub-question or END)
```

## Package layout

```
app/agent/
├── core/
│   ├── config.py       # AGENT_* settings (pydantic-settings)
│   ├── graph.py        # LangGraph compile → agent_app
│   ├── router.py       # route_action, route_after_finish, loop detection
│   └── state.py        # AgentState TypedDict
├── nodes/
│   ├── __init__.py     # async node implementations
│   └── finish_helpers.py
├── tools/
│   ├── base.py         # AgentTool protocol + ToolObservation + registry
│   ├── sql_tool.py
│   ├── retrieval_tool.py
│   ├── retrieval_cache.py
│   └── sql_engine/
│       ├── sql_generator.py
│       ├── schema_provider.py  # cached schema + table allow-list
│       └── validator.py        # sqlglot AST + single-session EXPLAIN/execute
├── prompts/
│   └── registry.py     # versioned prompt templates
├── eval/
│   └── harness.py      # offline golden-question routing eval
├── utils/              # llm, state, parsing, classification, retry, guardrails
├── observability/      # logging, metrics, tracing spans
└── schemas.py          # ActionDecision (Pydantic)
```

## Configuration

All settings use the `AGENT_` env prefix (see `app/agent/core/config.py`):

| Variable | Default | Description |
|---|---|---|
| `AGENT_MAX_STEPS_PER_SUBQUESTION` | 6 | ReAct loop cap per sub-question |
| `AGENT_MAX_SUBQUESTIONS` | 10 | Max decomposed parts |
| `AGENT_MAX_TOTAL_STEPS` | 50 | Total think steps across run |
| `AGENT_AGENT_TIMEOUT_SECONDS` | 120 | Wall-clock deadline |
| `AGENT_LLM_TIMEOUT_SECONDS` | 45 | Per LLM call timeout |
| `AGENT_SQL_QUERY_TIMEOUT_SECONDS` | 30 | DB statement timeout |
| `AGENT_SQL_MAX_ROWS` | 1000 | Max rows fetched |
| `AGENT_SQL_MAX_RESULT_ROWS_IN_PROMPT` | 20 | Rows shown to LLM |
| `AGENT_PROMPT_MAX_TOKENS` | 12000 | Context budget (~chars/4) |
| `AGENT_LLM_ROUTING_MODEL` | *(empty → generation model)* | Cheaper model for decompose/think/sql-gen |
| `AGENT_LLM_GENERATION_MODEL` | llama-3.3-70b-versatile | Answer/synthesis model |
| `AGENT_RUN_IDEMPOTENCY_ENABLED` | true | Cache completed runs by `run_id` |
| `AGENT_SQL_NAMESPACE` | *(empty)* | Comma-separated allowed tables |

## API entry points

- `POST /api/agent/ask-agent` — SSE stream (`agent_app.astream_events`)
- `POST /api/agent/ask-agent-batch` — JSON (`agent_app.ainvoke`)

Optional `run_id` in request body enables idempotent retries (Redis cache).

Initial state: `create_initial_state()` includes `run_id`, `start_time`, token/cost counters.

## Security

- SQL parsed with **sqlglot**; only `SELECT` / `UNION` allowed; multi-statement rejected.
- Tenant isolation via **bound parameters** (`:tenant_id`).
- Table/column allow-lists via `AGENT_SQL_NAMESPACE` / `AGENT_SQL_ALLOWED_COLUMNS`.
- Untrusted tool output sanitized; synthesis prompts label data as non-instructional.
- Basic numeric grounding check on final answers.

## Observability

- Structured logs: `run_id`, `tenant_id`, `node` via `observability/logging.py`
- Tracing spans per node via `observability/tracing.py`
- Prometheus:
  - `atlas_agent_node_executions_total`
  - `atlas_agent_node_duration_seconds`
  - `atlas_agent_tokens_total`
  - `atlas_agent_llm_cost_usd_total`
  - `atlas_agent_executions_total`

## Resilience

- LLM/DB **circuit breakers** (`utils/circuit_breaker.py`)
- **Retry** with exponential backoff (`tenacity`)
- **Loop detection** for repeated actions and sql↔retrieval oscillation
- Single DB session for EXPLAIN + execute

## Tests & eval

```bash
pytest tests/agent -v
```

Offline routing eval:

```bash
python -c "from app.agent.eval.harness import evaluate_routing_cases; print(evaluate_routing_cases())"
```

## Dependencies

Requires `sqlglot` and `tenacity` (see root `requirements.txt`).
