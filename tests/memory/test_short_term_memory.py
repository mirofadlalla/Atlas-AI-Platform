from app.memory.short_term_memory import ConversationTurn, ShortTermMemory


class FakePipeline:
    def __init__(self, store):
        self.store = store
        self.key = None
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def watch(self, key):
        self.key = key

    def get(self, key):
        return self.store.get(key)

    def multi(self):
        pass

    def setex(self, key, _ttl, value):
        self.key = key
        self.value = value

    def execute(self):
        self.store[self.key] = self.value


class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)

    def pipeline(self):
        return FakePipeline(self.store)


def test_short_term_memory_is_scoped_and_keeps_a_sliding_window(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(ShortTermMemory, "_client", staticmethod(lambda: client))
    memory = ShortTermMemory(ttl_seconds=60, max_turns=2)

    memory.save(
        "tenant-a", "user-a", "session-a", ConversationTurn("user", "first", "t1")
    )
    memory.save(
        "tenant-a", "user-a", "session-a", ConversationTurn("assistant", "second", "t2")
    )
    memory.save(
        "tenant-a", "user-a", "session-a", ConversationTurn("user", "third", "t3")
    )

    assert memory.load("tenant-a", "user-a", "session-a") == [
        {"role": "assistant", "content": "second", "timestamp": "t2"},
        {"role": "user", "content": "third", "timestamp": "t3"},
    ]
    assert memory.load("tenant-a", "user-b", "session-a") == []


def test_short_term_memory_skips_storage_without_a_session_id(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(ShortTermMemory, "_client", staticmethod(lambda: client))

    ShortTermMemory().save(
        "tenant-a", "user-a", None, {"role": "user", "content": "hello"}
    )

    assert client.store == {}
