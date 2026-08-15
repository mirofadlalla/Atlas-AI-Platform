"""Token counting with a safe approximation when tiktoken is unavailable."""

from __future__ import annotations


class TokenCounter:
    def __init__(self, model: str = "gpt-4o-mini") -> None:
        try:
            import tiktoken

            self._encoding = tiktoken.encoding_for_model(model)
        except Exception:
            self._encoding = None

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self._encoding:
            return len(self._encoding.encode(text))
        return max(1, (len(text) + 3) // 4)

    def truncate(
        self, text: str, max_tokens: int, suffix: str = "\n...[truncated]"
    ) -> str:
        if max_tokens <= 0:
            return ""
        if self.count(text) <= max_tokens:
            return text
        if not self._encoding:
            return text[: max(0, max_tokens * 4 - len(suffix))] + suffix
        suffix_tokens = self._encoding.encode(suffix)
        budget = max(0, max_tokens - len(suffix_tokens))
        return self._encoding.decode(self._encoding.encode(text)[:budget]) + suffix

    def windows(self, text: str, token_size: int, overlap: int) -> list[str]:
        """Split text into real tokenizer windows with a token overlap."""
        if token_size <= overlap:
            raise ValueError("token_size must be greater than overlap")
        if self._encoding:
            tokens = self._encoding.encode(text)
            return [
                self._encoding.decode(tokens[start : start + token_size])
                for start in range(0, len(tokens), token_size - overlap)
            ]
        # Only used when tiktoken is unavailable; preserves the same bounded-window contract.
        width, step = token_size * 4, (token_size - overlap) * 4
        return [text[start : start + width] for start in range(0, len(text), step)]
