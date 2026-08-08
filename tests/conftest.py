"""
Root conftest.py — sets the minimum environment variables required by
``app.core.config.Settings()`` before any test module is collected.

Why this exists
---------------
``app/core/config.py`` ends with the module-level statement::

    settings = Settings()

``Settings`` inherits from ``pydantic_settings.BaseSettings`` and validates
required fields (``api_secret_key``, ``postgres_pass``) on instantiation.
Because Python executes module-level code at import time, *any* test that
imports *any* application module will trigger this validation.

Without the env vars below, pytest fails during collection — before a single
test function runs — with::

    pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
    api_secret_key
      Field required [type=missing, ...]

The values supplied here are test-only placeholders; they grant no database
or API access.  Real secrets must still be configured in CI/CD secrets and in
the production ``.env`` file.

No LLM calls are made during unit tests — all Groq interactions are mocked —
so setting an empty ``GROQ_API_KEY`` is safe.
"""

import os

# ---------------------------------------------------------------------------
# Minimal environment required for Settings() to instantiate.
# setdefault() means we never override values already present in the
# environment (e.g. real values injected by the CI integration-tests job).
# ---------------------------------------------------------------------------
os.environ.setdefault("API_SECRET_KEY", "ci-unit-test-secret-not-for-production")
os.environ.setdefault("POSTGRES_PASS", "ci-unit-test-pass")
os.environ.setdefault("POSTGRES_USER", "ci_user")
os.environ.setdefault("POSTGRES_DB", "ci_test")
os.environ.setdefault("POSTGRES_HOST", "localhost")

# Groq SDK constructor does not validate the key; it is only used when making
# real API calls.  Unit tests mock all LLM interactions, so an empty key is safe.
os.environ.setdefault("GROQ_API_KEY", "")

# Redis password — ShortTermMemory and other Redis clients fail open (log a
# warning and continue) when Redis is unavailable in unit tests.
os.environ.setdefault("REDIS_PASSWORD", "")
