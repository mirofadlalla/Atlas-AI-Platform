"""Cached, allow-list-aware database schema descriptions for SQL generation."""

from __future__ import annotations

import logging
import time

from sqlalchemy import inspect

from app.agent.core.config import agent_settings
from app.core.db import data_base

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, str]] = {}


def get_schema_description(
    force_refresh: bool = False,
    tenant_id: str | None = None,
    allowed_tables: set[str] | None = None,
) -> str:
    """
    Return a text description of the database schema visible to the current tenant.

    Parameters
    ----------
    force_refresh:
        Bypass the in-memory cache and re-inspect the database.
    tenant_id:
        Used as part of the cache key so each tenant's schema view is stored
        separately.  This is critical in multi-tenant deployments where tenants
        have different ``allowed_tables`` configurations.
    allowed_tables:
        Explicit set of tables this tenant may see.  If ``None``, falls back to
        ``agent_settings.allowed_tables`` (the global ``AGENT_SQL_NAMESPACE``
        env var).  Callers should pass the tenant-specific allow-list here once
        per-tenant table configuration is stored in the database.
    """
    effective_tables = (
        allowed_tables if allowed_tables is not None else agent_settings.allowed_tables
    )

    # Build a cache key that is tenant-specific so tenants with different table
    # configurations never share a cached schema description.
    tenant_label = tenant_id or "__global__"
    tables_label = ",".join(sorted(effective_tables)) if effective_tables else "__all__"
    cache_key = f"{tenant_label}:{tables_label}"

    now = time.time()
    if not force_refresh and cache_key in _cache:
        cached_at, cached_value = _cache[cache_key]
        if now - cached_at < agent_settings.schema_cache_ttl_seconds:
            return cached_value

    inspector = inspect(data_base)
    schema_text = ""

    for table in inspector.get_table_names():
        if effective_tables is not None and table not in effective_tables:
            continue
        columns = inspector.get_columns(table)
        schema_text += f"\nTable: {table}\n"
        for col in columns:
            col_name = col["name"]
            if (
                agent_settings.allowed_columns
                and col_name not in agent_settings.allowed_columns
            ):
                continue
            schema_text += f" - {col_name} ({col['type']})\n"

    if not schema_text.strip():
        logger.warning(
            "Schema description is empty for tenant=%s; "
            "check AGENT_SQL_NAMESPACE / DB connectivity",
            tenant_label,
        )

    _cache[cache_key] = (now, schema_text)
    return schema_text


def invalidate_schema_cache() -> None:
    _cache.clear()
