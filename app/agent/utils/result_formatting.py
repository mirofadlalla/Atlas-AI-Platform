"""Format SQL result rows for LLM prompts with size limits."""

from __future__ import annotations

from typing import Any

from app.agent.core.config import agent_settings


def format_sql_results(rows: list[Any], max_rows: int | None = None) -> tuple[str, bool]:
    max_rows = max_rows or agent_settings.sql_max_result_rows_in_prompt
    if not rows:
        return "No results found", False

    formatted: list[dict[str, Any]] = []
    for row in rows[: max(agent_settings.sql_max_rows, max_rows)]:
        if hasattr(row, "keys"):
            formatted.append(dict(zip(row.keys(), row)))
        elif hasattr(row, "_mapping"):
            formatted.append(dict(row._mapping))
        else:
            formatted.append({"value": row})

    preview = formatted[:max_rows]
    has_data = len(formatted) > 0
    result_str = f"Found {len(formatted)} record(s)"
    if len(formatted) > max_rows:
        result_str += f" (showing first {max_rows})"
    result_str += ":\n" + str(preview)
    return result_str, has_data
