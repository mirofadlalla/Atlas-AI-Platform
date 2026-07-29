"""Prompt size limits and context truncation."""

from __future__ import annotations

from app.agent.core.config import agent_settings


def truncate_context(text: str, max_chars: int | None = None, label: str = "context") -> str:
    limit = max_chars or agent_settings.max_prompt_chars
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}\n... [{label} truncated, {omitted} chars omitted]"


def estimate_chars(*parts: str) -> int:
    return sum(len(p) for p in parts)
