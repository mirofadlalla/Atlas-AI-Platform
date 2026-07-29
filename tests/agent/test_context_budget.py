from app.agent.utils.context_budget import truncate_to_char_budget, truncate_to_token_budget


def test_truncate_to_char_budget():
    text = "a" * 100
    out = truncate_to_char_budget(text, 20)
    assert len(out) <= 20
    assert out.endswith("...[truncated]")


def test_truncate_to_token_budget_keeps_short_text():
    assert truncate_to_token_budget("hello", 100) == "hello"
