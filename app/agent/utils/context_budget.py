"""Prompt context size limits with language-aware token estimation.

The old ``len(text) // 4`` heuristic assumed English throughout (≈ 4 chars/token).
Arabic and other non-Latin scripts tokenize at ≈ 1–2 tokens/character in BPE
vocabularies, making the old estimate off by 2–3× for bilingual prompts.

Strategy (in priority order):
1. Use ``tiktoken`` for exact counts when it is installed.
2. Fall back to a character-class heuristic that applies separate rates for
   ASCII (≈ 4 chars/token) and non-ASCII (≈ 1 char/token) characters.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Tiktoken-backed estimator (best accuracy, optional dependency)
# ---------------------------------------------------------------------------
try:
    import tiktoken as _tiktoken

    _enc = _tiktoken.get_encoding("cl100k_base")

    def estimate_chars_as_tokens(text: str) -> int:
        """Exact token count via tiktoken cl100k_base encoding."""
        return max(1, len(_enc.encode(text)))

except ImportError:  # pragma: no cover — tiktoken not installed
    # ---------------------------------------------------------------------------
    # Heuristic fallback — language-aware character-class rates
    # ---------------------------------------------------------------------------
    def estimate_chars_as_tokens(text: str) -> int:  # type: ignore[misc]
        """
        Language-aware token estimate.

        - ASCII (Latin, digits, punctuation): ≈ 4 chars per token.
        - Non-ASCII (Arabic, CJK, emoji, …): ≈ 1 char per token (conservative).

        This is a deliberate over-count for non-Latin text so that callers err
        on the side of truncating earlier rather than overflowing the context.
        """
        ascii_count = sum(1 for c in text if ord(c) < 128)
        non_ascii_count = len(text) - ascii_count
        return max(1, (ascii_count // 4) + non_ascii_count)


# ---------------------------------------------------------------------------
# Char / token budget helpers
# ---------------------------------------------------------------------------


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
    """Truncate *text* so its estimated token count stays within *max_tokens*."""
    if estimate_chars_as_tokens(text) <= max_tokens:
        return text
    # Binary-search for the largest prefix that fits.
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if estimate_chars_as_tokens(text[:mid]) <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    keep = max(0, lo - len(suffix))
    return text[:keep] + suffix
