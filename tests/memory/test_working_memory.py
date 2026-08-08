from app.memory.token_counter import TokenCounter
from app.memory.working_memory import WorkingMemory


def test_working_memory_respects_priority_and_total_budget():
    counter = TokenCounter()
    memory = WorkingMemory(max_tokens=8, token_counter=counter)
    memory.add("low", "one two three four", priority=5)
    memory.add("high", "one two", priority=1)

    assembled = memory.assemble()

    assert "=== HIGH ===" in assembled
    assert memory.tokens_used <= 8
    assert memory.context_sources[0] == "high"


def test_working_memory_truncates_per_source_limit():
    counter = TokenCounter()
    memory = WorkingMemory(max_tokens=20, token_counter=counter)
    memory.add("history", "x" * 100, priority=1, max_tokens=2)

    assembled = memory.assemble()

    assert counter.count(assembled) <= 20
    assert memory.tokens_used <= 20
