from sqlalchemy.orm import Session


class IngestController:
    """
    Controller for handling RAG data ingestion requests.
    """

    @staticmethod
    def ingest_file(
        file_path: str, tenant_id: int, source: str, author: str, db: Session
    ):
        from app.services.rag_services.ingest_rag_service import ingest_file_task

        try:
            # send task to Celery with proper error handling
            task = ingest_file_task.delay(file_path, tenant_id, source, author)

            # return task ID and status
            return {"task_id": task.id, "status": "queued", "success": True}
        except Exception as e:
            return {"error": str(e), "status": "failed", "success": False}
