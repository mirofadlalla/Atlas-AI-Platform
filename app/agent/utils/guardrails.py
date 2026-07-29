"""Lightweight output guardrails for agent answers."""

from __future__ import annotations

import re

_INJECTION_PATTERNS = (
    r"ignore\s+(all\s+)?prior\s+instructions",
    r"disregard\s+(the\s+)?(above|previous)",
    r"you\s+are\s+now\s+",
    r"system\s+prompt\s*:",
)


def sanitize_untrusted_block(text: str) -> str:
    """Neutralize obvious instruction-injection phrases in untrusted tool output."""
    cleaned = text
    for pattern in _INJECTION_PATTERNS:
        cleaned = re.sub(pattern, "[filtered]", cleaned, flags=re.IGNORECASE)
    return cleaned


def validate_answer_grounding(answer: str, source_text: str) -> tuple[str, bool]:
    """
    Flag answers that cite numeric values absent from source data.
    Returns (possibly annotated answer, passed).
    """
    if not source_text.strip():
        return answer, True

    cited_numbers = set(re.findall(r"\b\d[\d,]*\.?\d*\b", answer))
    if not cited_numbers:
        return answer, True

    source_numbers = set(re.findall(r"\b\d[\d,]*\.?\d*\b", source_text))
    ungrounded = [n for n in cited_numbers if n.replace(",", "") not in {
        s.replace(",", "") for s in source_numbers
    }]
    if not ungrounded:
        return answer, True

    note = (
        "\n\n(Note: some numeric values in this answer could not be verified "
        "against retrieved data.)"
    )
    return answer + note, False
