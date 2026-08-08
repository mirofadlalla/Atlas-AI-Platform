"""Prompt context size limits."""

from __future__ import annotations


def estimate_chars_as_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token for English)."""
    return max(1, len(text) // 4)  # 4 Characters ≈ 1 Token


def truncate_to_char_budget(
    text: str, max_chars: int, suffix: str = "\n...[truncated]"
) -> str:
    if len(text) <= max_chars:
        return text
    keep = max(0, max_chars - len(suffix))
    return text[:keep] + suffix


def truncate_to_token_budget(
    text: str, max_tokens: int, suffix: str = "\n...[truncated]"
) -> str:
    max_chars = max_tokens * 4
    return truncate_to_char_budget(text, max_chars, suffix=suffix)
