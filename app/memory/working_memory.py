"""Priority-based, per-request prompt-context assembly."""

from __future__ import annotations

from dataclasses import dataclass

from app.memory.token_counter import TokenCounter


@dataclass(frozen=True)
class ContextItem:
    source: str
    content: str
    priority: int
    max_tokens: int | None = None


class WorkingMemory:
    """Fits useful context into a fixed token budget without storing it."""

    def __init__(self, max_tokens: int, token_counter: TokenCounter | None = None) -> None:
        self.max_tokens = max_tokens
        self.counter = token_counter or TokenCounter()
        self._items: list[ContextItem] = []
        self.context_sources: list[str] = []
        self.tokens_used = 0

    def add(self, source: str, content: str | None, priority: int, max_tokens: int | None = None) -> "WorkingMemory":
        if content and content.strip():
            self._items.append(ContextItem(source, content.strip(), priority, max_tokens))
        return self

    def assemble(self) -> str:
        parts: list[str] = []
        remaining = self.max_tokens
        self.context_sources = []
        for item in sorted(self._items, key=lambda candidate: candidate.priority):
            header = f"=== {item.source.upper()} ===\n"
            header_tokens = self.counter.count(header)
            if header_tokens >= remaining:
                continue
            allowed = remaining - header_tokens
            if item.max_tokens is not None:
                allowed = min(allowed, item.max_tokens)
            content = self.counter.truncate(item.content, allowed)
            rendered = header + content
            tokens = self.counter.count(rendered)
            if not content or tokens > remaining:
                continue
            parts.append(rendered)
            self.context_sources.append(item.source)
            remaining -= tokens
        self.tokens_used = self.max_tokens - remaining
        return "\n\n".join(parts)
