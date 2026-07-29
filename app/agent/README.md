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
│   ├── router.py       # route_action, route_after_finish
│   └── state.py        # AgentState TypedDict
├── nodes/
│   ├── __init__.py     # async node implementations
│   └── finish_helpers.py
├── tools/
│   ├── base.py         # AgentTool protocol + registry
│   ├── sql_tool.py
│   ├── retrieval_tool.py
│   ├── retrieval_cache.py
│   └── sql_engine/
│       ├── sql_generator.py
│       ├── schema_provider.py  # cached schema + table allow-list
│       └── validator.py        # sqlglot AST validation + tenant bind
├── utils/              # state, parsing, classification, retry, db session
├── observability/      # structured log helpers + Prometheus node metrics
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
| `AGENT_SQL_QUERY_TIMEOUT_SECONDS` | 30 | DB statement timeout |
| `AGENT_SQL_MAX_ROWS` | 1000 | Max rows fetched |
| `AGENT_SQL_MAX_RESULT_ROWS_IN_PROMPT` | 20 | Rows shown to LLM |
| `AGENT_SQL_MAX_ALLOWED_COST` | 1000 | EXPLAIN cost ceiling |
| `AGENT_SQL_NAMESPACE` | *(empty)* | Comma-separated allowed tables |
| `AGENT_SCHEMA_CACHE_TTL_SECONDS` | 300 | Schema reflection cache |
| `AGENT_RETRIEVAL_CACHE_TTL_SECONDS` | 300 | Redis retrieval cache TTL |

## API entry points

- `POST /api/agent/ask-agent` — SSE stream (`agent_app.astream_events`)
- `POST /api/agent/ask-agent-batch` — JSON (`agent_app.ainvoke`)

Initial state is built via `create_initial_state()` in `app/agent/utils/state_helpers.py`
(`run_id`, `start_time`, budget counters included).

## Security

- SQL is parsed with **sqlglot**; only `SELECT` (and `UNION` of selects) is allowed.
- Tenant isolation uses **bound parameters** (`:tenant_id`), not string interpolation.
- Optional table/column allow-lists via `AGENT_SQL_NAMESPACE`.
- Tool outputs are framed as untrusted data in synthesis prompts.

## Observability

- Structured log context: `run_id`, `tenant_id`, `node` via `app/agent/observability/logging.py`
- Prometheus: `atlas_agent_node_executions_total`, `atlas_agent_node_duration_seconds`
- Route-level metrics remain in `app/routes/agent_route.py` + `app/core/monitors.py`

## Tests

```bash
pytest tests/agent -v
```

## Dependencies

Requires `sqlglot` and `tenacity` (see root `requirements.txt`).
