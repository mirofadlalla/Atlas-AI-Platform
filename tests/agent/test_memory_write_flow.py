from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.nodes.memory_nodes import memory_write_node


@pytest.mark.asyncio
async def test_memory_write_queues_a_fact_as_the_completed_turn():
    memory = MagicMock()
    state = {
        "tenant_id": "tenant-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "question": "My preferred language is Arabic",
        "final_answer": "I will remember that preference.",
        # An earlier turn must not be sent to the episodic writer again.
        "conversation_history": [
            {"role": "user", "content": "old question"},
            {"role": "assistant", "content": "old answer"},
        ],
    }

    with (
        patch("app.agent.nodes.memory_nodes.ShortTermMemory", return_value=memory),
        patch("app.agent.nodes.memory_nodes.emit_node_status", new=AsyncMock()),
        patch("app.agent.nodes.memory_nodes.emit_thought_chunk", new=AsyncMock()),
        patch("app.agent.nodes.memory_nodes.trigger_semantic_memory_extraction") as semantic,
        patch("app.agent.nodes.memory_nodes.trigger_episode_write") as episodic,
    ):
        await memory_write_node(state)

    assert memory.save.call_count == 2
    semantic.assert_called_once_with(
        "My preferred language is Arabic",
        "I will remember that preference.",
        "user-1",
        "tenant-1",
    )
    episodic.assert_called_once_with(
        "session-1",
        [
            {"role": "user", "content": "My preferred language is Arabic"},
            {"role": "assistant", "content": "I will remember that preference."},
        ],
        "user-1",
        "tenant-1",
    )
    memory.load.assert_not_called()


@pytest.mark.asyncio
async def test_memory_write_does_not_queue_long_term_writes_for_a_normal_turn():
    memory = MagicMock()
    state = {
        "tenant_id": "tenant-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "question": "Hi",
        "final_answer": "Hello! How can I help?",
        "conversation_history": [],
    }

    with (
        patch("app.agent.nodes.memory_nodes.ShortTermMemory", return_value=memory),
        patch("app.agent.nodes.memory_nodes.emit_node_status", new=AsyncMock()),
        patch("app.agent.nodes.memory_nodes.emit_thought_chunk", new=AsyncMock()),
        patch("app.agent.nodes.memory_nodes.trigger_semantic_memory_extraction") as semantic,
        patch("app.agent.nodes.memory_nodes.trigger_episode_write") as episodic,
    ):
        await memory_write_node(state)

    assert memory.save.call_count == 2
    semantic.assert_not_called()
    episodic.assert_not_called()
