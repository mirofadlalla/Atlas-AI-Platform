"""Cached, allow-list-aware database schema descriptions for SQL generation."""

from __future__ import annotations

import logging
import time

from sqlalchemy import inspect

from app.agent.core.config import agent_settings
from app.core.db import data_base

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, str]] = {}


def get_schema_description(force_refresh: bool = False) -> str:
    cache_key = agent_settings.sql_namespace or "__all__"
    now = time.time()

    if not force_refresh and cache_key in _cache:
        cached_at, cached_value = _cache[cache_key]
        # Check if the cached value is still valid based on the TTL setting
        if now - cached_at < agent_settings.schema_cache_ttl_seconds:
            return cached_value

    inspector = inspect(data_base)
    allowed = agent_settings.allowed_tables
    schema_text = ""

    for table in inspector.get_table_names():
        if allowed is not None and table not in allowed:
            continue
        columns = inspector.get_columns(table)
        schema_text += f"\nTable: {table}\n"
        for col in columns:
            col_name = col["name"]
            if agent_settings.allowed_columns and col_name not in agent_settings.allowed_columns:
                continue
            schema_text += f" - {col_name} ({col['type']})\n"

    if not schema_text.strip():
        logger.warning("Schema description is empty; check AGENT_SQL_NAMESPACE / DB connectivity")

    _cache[cache_key] = (now, schema_text)
    return schema_text


def invalidate_schema_cache() -> None:
    _cache.clear()
