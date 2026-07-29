from app.agent.utils.parsing import extract_first_json_block


def test_extract_first_json_block_from_markdown_fence():
    text = 'Here is data:\n```json\n{"action": "sql", "thought": "need data"}\n```'
    parsed = extract_first_json_block(text)
    assert '"action": "sql"' in parsed


def test_extract_first_json_block_plain_object():
    text = 'prefix {"a": 1, "b": {"c": 2}} suffix'
    parsed = extract_first_json_block(text)
    assert parsed == '{"a": 1, "b": {"c": 2}}'
