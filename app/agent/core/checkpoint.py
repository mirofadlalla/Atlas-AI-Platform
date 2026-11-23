"""
LangGraph checkpointer factory.

Provides a lazy singleton checkpointer (SQLite for dev, Postgres for prod)
configured via AgentSettings. Falls back gracefully to None if the required
packages are not installed, so the app still starts without checkpointing.
"""

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional imports — the app starts even without these packages installed.
# ---------------------------------------------------------------------------
try:
    from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore
    _sqlite_available = True
except ImportError:
    SqliteSaver = None  # type: ignore
    _sqlite_available = False
    logger.warning(
        "langgraph-checkpoint-sqlite is not installed. "
        "SQLite checkpointing will be unavailable. "
        "Install it with: pip install langgraph-checkpoint-sqlite aiosqlite"
    )

try:
    from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore
    _postgres_available = True
except ImportError:
    PostgresSaver = None  # type: ignore
    _postgres_available = False
    logger.warning(
        "langgraph-checkpoint-postgres is not installed. "
        "Postgres checkpointing will be unavailable. "
        "Install it with: pip install langgraph-checkpoint-postgres 'psycopg[binary]'"
    )

# ---------------------------------------------------------------------------
# Singleton state
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_checkpointer_instance = None
_checkpointer_initialized = False


def _derive_postgres_url() -> str:
    """
    Return a psycopg3-compatible postgres URL for the checkpointer.

    Priority:
    1. agent_settings.checkpoint_db_url (if non-empty)
    2. settings.DATABASE_URL with psycopg2 → psycopg driver substitution
    """
    try:
        from app.agent.core.config import agent_settings

        if agent_settings.checkpoint_db_url:
            return agent_settings.checkpoint_db_url
    except Exception:
        pass

    try:
        from app.core.config import settings

        url: str = settings.DATABASE_URL
        # Replace SQLAlchemy psycopg2 dialect with bare psycopg (psycopg3)
        url = url.replace("postgresql+psycopg2://", "postgresql+psycopg://")
        url = url.replace("postgres+psycopg2://", "postgresql+psycopg://")
        # Strip the SQLAlchemy dialect prefix so the raw driver URL is returned
        url = url.replace("postgresql+psycopg://", "postgresql://")
        return url
    except Exception as exc:
        logger.warning("Could not derive postgres URL for checkpointer: %s", exc)
        return ""


def get_checkpointer():
    """
    Return the singleton checkpointer instance (SqliteSaver or PostgresSaver).

    Returns None if:
    - The required package is not installed.
    - Configuration is missing / invalid.

    Thread-safe via a module-level lock.
    """
    global _checkpointer_instance, _checkpointer_initialized

    if _checkpointer_initialized:
        return _checkpointer_instance

    with _lock:
        # Double-checked locking
        if _checkpointer_initialized:
            return _checkpointer_instance

        try:
            from app.agent.core.config import agent_settings

            backend = agent_settings.checkpoint_backend.lower()

            if backend == "sqlite":
                if not _sqlite_available:
                    logger.warning(
                        "checkpoint_backend='sqlite' but langgraph-checkpoint-sqlite "
                        "is not installed. Checkpointing disabled."
                    )
                    _checkpointer_instance = None
                else:
                    db_path = agent_settings.checkpoint_sqlite_path or "./atlas_checkpoints.db"
                    _checkpointer_instance = SqliteSaver.from_conn_string(db_path)
                    logger.info(
                        "LangGraph SQLite checkpointer configured at: %s", db_path
                    )

            elif backend == "postgres":
                if not _postgres_available:
                    logger.warning(
                        "checkpoint_backend='postgres' but langgraph-checkpoint-postgres "
                        "is not installed. Checkpointing disabled."
                    )
                    _checkpointer_instance = None
                else:
                    pg_url = _derive_postgres_url()
                    if not pg_url:
                        logger.warning(
                            "No postgres URL available for checkpointer. "
                            "Set AGENT_CHECKPOINT_DB_URL or DATABASE_URL."
                        )
                        _checkpointer_instance = None
                    else:
                        _checkpointer_instance = PostgresSaver.from_conn_string(pg_url)
                        logger.info("LangGraph Postgres checkpointer configured.")

            else:
                logger.warning(
                    "Unknown checkpoint_backend=%r. Checkpointing disabled.", backend
                )
                _checkpointer_instance = None

        except Exception as exc:
            logger.warning(
                "Failed to initialise LangGraph checkpointer: %s. "
                "Continuing without checkpointing.",
                exc,
            )
            _checkpointer_instance = None

        _checkpointer_initialized = True

    return _checkpointer_instance


async def setup_checkpointer() -> None:
    """
    Async setup — calls `.setup()` on the checkpointer to create tables.

    Safe to call even when the checkpointer is None (no-op).
    """
    checkpointer = get_checkpointer()
    if checkpointer is None:
        logger.info("No checkpointer configured; skipping setup.")
        return

    try:
        setup_fn = getattr(checkpointer, "setup", None)
        if setup_fn is None:
            return

        import asyncio
        import inspect

        if inspect.iscoroutinefunction(setup_fn):
            await setup_fn()
        else:
            # SqliteSaver.setup() is synchronous — run in executor to stay async-friendly
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, setup_fn)

        logger.info("LangGraph checkpointer tables created/verified.")
    except Exception as exc:
        logger.warning("Checkpointer setup error (non-fatal): %s", exc)
