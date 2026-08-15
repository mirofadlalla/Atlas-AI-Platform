import pytest

from app.memory.memory_manager import MemoryManager


class FakeRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, _ttl, value):
        self.values[key] = value


@pytest.mark.asyncio
async def test_short_term_reloads_while_long_term_context_is_cached(monkeypatch):
    manager = MemoryManager()
    redis = FakeRedis()
    short_term_calls = []
    semantic_calls = []
    episodic_calls = []

    manager.short_term.load = lambda *_: short_term_calls.append(1) or [
        {"role": "user", "content": f"turn {len(short_term_calls)}"}
    ]
    manager.semantic.recall = lambda *args: semantic_calls.append(args) or ["Prefers Arabic"]
    manager.episodic.get_recent = lambda *args, **kwargs: episodic_calls.append(
        (args, kwargs)
    ) or ["Previous session summary"]
    monkeypatch.setattr(manager, "_redis_client", lambda: redis)

    first = await manager.load_fast_context("tenant-1", "user-1", "session-1", "first")
    second = await manager.load_fast_context("tenant-1", "user-1", "session-1", "second")

    assert first["conversation_history"] != second["conversation_history"]
    assert len(short_term_calls) == 2
    assert len(semantic_calls) == 1
    assert len(episodic_calls) == 1
    assert second["recalled_memories"] == ["Prefers Arabic"]
    assert second["episode_context"] == "- Previous session summary"
