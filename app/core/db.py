from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

data_base = create_engine(
    settings.DATABASE_URL, 
    pool_pre_ping=True
)

Sessions = sessionmaker(
    autoflush=False,
    autocommit=False,

    bind=data_base
)

def get_db():
    db = Sessions()
    try :
        yield db
    finally:
        db.close()

def get_db_session():
    """
    Returns a new database session directly (not a generator).
    Use this in Celery tasks or other background processes.
    """
    db = Sessions()
    try:
        return db
    except Exception:
        db.close()
        raise