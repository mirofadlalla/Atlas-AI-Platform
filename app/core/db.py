from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_recycle=1800,
    pool_pre_ping=True,
)

Sessions = sessionmaker(
    autoflush=False,
    autocommit=False,
    bind=engine,
)


def get_db():
    """
    FastAPI dependency that yields a database session and guarantees it is
    closed when the request finishes, even if an exception is raised.
    """
    db = Sessions()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session():
    """
    Context-manager wrapper for use in Celery tasks and other non-FastAPI
    code that cannot use Depends.
    """
    db: Session = Sessions()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
