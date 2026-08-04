"""Database session context manager for agent SQL operations."""

from app.core.db import get_db_session

# Re-export the context manager from db.py directly.
# Previously this file had its own wrapper that called get_db_session() as a
# plain function and duplicated the close/cleanup logic.  Now that db.py
# exposes get_db_session() as a proper @contextmanager, we simply re-export it
# under the name the agent utils already use.
agent_db_session = get_db_session
