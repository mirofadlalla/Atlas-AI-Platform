"""Database session context manager for agent SQL operations."""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session

from app.core.db import get_db_session


@contextmanager
def agent_db_session() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()
