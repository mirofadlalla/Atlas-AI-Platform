# app/services/ingest_rag_service.py
from app.celery.celery_config import celery_app
from app.core.db import get_db_session


# Celery task for ingesting RAG data
@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
    time_limit=600,
    soft_time_limit=550
)
def ingest_file_task(self, file_path: str, tenant_id: str, source: str, author: str):
    """
    Async task to ingest files into RAG pipeline.
    Imports RAGPipeline here to avoid loading heavy dependencies during worker startup.

    The database session is managed via a context manager so it is always
    closed and rolled back on exception — preventing connection pool leaks
    inside long-lived Celery worker processes.
    """
    try:
        from app.rag.ingest_data_pipline import RAGPipeline

        custom_metadata = {
            "tenant_id": tenant_id,
            "source": source,
            "author": author,
        }

        # Use context manager — session is closed even if process_file raises.
        with get_db_session() as db:
            return RAGPipeline.process_file(
                file_path=file_path,
                custom_metadata=custom_metadata,
                db=db,
            )
    except MemoryError:
        self.retry(countdown=60, exc=MemoryError("Not enough memory to process file"), max_retries=3)
    except Exception as exc:
        self.retry(countdown=10, exc=exc)
