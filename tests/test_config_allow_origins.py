"""
Regression tests for ``app.core.config.Settings.allow_origins_list``.

These tests guard against the ``AttributeError: 'list' object has no
attribute 'split'`` crash that occurred in CI when pydantic-settings v2
parsed the ``ALLOW_ORIGINS`` environment variable into a ``list[str]``
before ``allow_origins_list`` tried to call ``.split(",")`` on it.

Test cases
----------
A  — comma-separated string   →  list[str]
B  — list input               →  same list (identity)
C  — whitespace around values →  stripped list
D  — empty / blank entries    →  filtered list
E  — single origin string     →  single-element list
F  — single-element list      →  single-element list (no spurious split)
"""

import pytest


# ---------------------------------------------------------------------------
# Helper: instantiate a Settings object with allow_origins forced to a
# specific value without touching the environment or the real singleton.
# We monkeypatch the instance attribute directly on a fresh Settings copy.
# ---------------------------------------------------------------------------


def _make_settings(allow_origins_value):
    """Return a Settings instance with allow_origins overridden to *value*.

    We import Settings inside the function to avoid module-level issues
    and construct it from the environment (conftest.py seeds the required
    variables).  We then directly override the field value on the instance
    — Pydantic v2 model instances support attribute assignment by default
    (model_config does not forbid it here).
    """
    from app.core.config import Settings

    s = Settings()
    # Override the field on the live instance so allow_origins_list sees it.
    object.__setattr__(s, "allow_origins", allow_origins_value)
    return s


# ---------------------------------------------------------------------------
# Case A — comma-separated string
# ---------------------------------------------------------------------------


def test_allow_origins_list_from_comma_string():
    """Comma-separated string is split and stripped correctly."""
    s = _make_settings(
        "https://atlas-ai-frontend-tafu.vercel.app,http://localhost:5173"
    )
    assert s.allow_origins_list == [
        "https://atlas-ai-frontend-tafu.vercel.app",
        "http://localhost:5173",
    ]


# ---------------------------------------------------------------------------
# Case B — list input (the path that caused the AttributeError in CI)
# ---------------------------------------------------------------------------


def test_allow_origins_list_from_list():
    """When allow_origins is already a list it is returned as-is (no split crash)."""
    origins = [
        "https://atlas-ai-frontend-tafu.vercel.app",
        "http://localhost:5173",
    ]
    s = _make_settings(origins)
    assert s.allow_origins_list == origins


# ---------------------------------------------------------------------------
# Case C — whitespace
# ---------------------------------------------------------------------------


def test_allow_origins_list_strips_whitespace_string():
    """Leading/trailing whitespace around origins is stripped (string input)."""
    s = _make_settings(
        "https://example.com,  http://localhost:5173  "
    )
    assert s.allow_origins_list == [
        "https://example.com",
        "http://localhost:5173",
    ]


def test_allow_origins_list_strips_whitespace_list():
    """Leading/trailing whitespace around origins is stripped (list input)."""
    s = _make_settings(
        ["  https://example.com  ", "http://localhost:5173  "]
    )
    assert s.allow_origins_list == [
        "https://example.com",
        "http://localhost:5173",
    ]


# ---------------------------------------------------------------------------
# Case D — empty / blank entries filtered out
# ---------------------------------------------------------------------------


def test_allow_origins_list_filters_empty_entries_string():
    """Empty / blank entries in a comma-separated string are dropped."""
    s = _make_settings("https://example.com, ,http://localhost:5173,")
    assert s.allow_origins_list == [
        "https://example.com",
        "http://localhost:5173",
    ]


def test_allow_origins_list_filters_empty_entries_list():
    """Empty / blank entries inside a list are dropped."""
    s = _make_settings(
        ["https://example.com", "  ", "", "http://localhost:5173"]
    )
    assert s.allow_origins_list == [
        "https://example.com",
        "http://localhost:5173",
    ]


# ---------------------------------------------------------------------------
# Case E — single origin as string
# ---------------------------------------------------------------------------


def test_allow_origins_list_single_origin_string():
    """A single origin string (no comma) becomes a single-element list."""
    s = _make_settings("https://atlas-ai-frontend-tafu.vercel.app")
    assert s.allow_origins_list == ["https://atlas-ai-frontend-tafu.vercel.app"]


# ---------------------------------------------------------------------------
# Case F — single-element list is returned unchanged
# ---------------------------------------------------------------------------


def test_allow_origins_list_single_element_list():
    """A single-element list is returned as a single-element list (no split)."""
    s = _make_settings(["https://atlas-ai-frontend-tafu.vercel.app"])
    assert s.allow_origins_list == ["https://atlas-ai-frontend-tafu.vercel.app"]


# ---------------------------------------------------------------------------
# Invariant: return type is always list[str]
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "https://a.com,https://b.com",
        ["https://a.com", "https://b.com"],
        "https://a.com",
        ["https://a.com"],
        "",
        [],
    ],
)
def test_allow_origins_list_always_returns_list(value):
    """allow_origins_list always returns list[str], regardless of input type."""
    s = _make_settings(value)
    result = s.allow_origins_list
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, str)


# ---------------------------------------------------------------------------
# Smoke test: the real singleton from the module can be imported cleanly
# (this is what was crashing at collection time in CI)
# ---------------------------------------------------------------------------


def test_real_settings_import_and_allow_origins_list():
    """The module-level settings singleton imports without AttributeError."""
    from app.core.config import settings

    result = settings.allow_origins_list
    assert isinstance(result, list), f"Expected list, got {type(result)}"
    # Every element must be a non-empty string
    for origin in result:
        assert isinstance(origin, str)
        assert origin  # no blank entries survive
