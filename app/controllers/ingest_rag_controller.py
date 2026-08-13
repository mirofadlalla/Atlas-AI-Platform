"""
Ingest RAG controller.

Handles file validation, chunked disk write, MLflow tracking, and Celery
task queuing for the RAG ingestion pipeline.
"""

import logging
import uuid
from pathlib import Path
from fastapi import HTTPException, UploadFile

# MLflowService is imported lazily inside upload_file() to avoid pulling
# mlflow (and its pkg_resources dependency) at module import time, which
# breaks test environments that do not have all optional dependencies installed.

logger = logging.getLogger(__name__)

# ── Security constants ────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS: set[str] = {
    ".pdf",
    ".txt",
    ".md",
    ".csv",
    ".docx",
    ".doc",
    ".pptx",
    ".ppt",
    ".xlsx",
    ".xls",
    ".html",
    ".json",
}
MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB
UPLOAD_CHUNK_SIZE: int = 1024 * 1024  # 1 MB


def _safe_filename(original: str) -> str:
    """Strip directory components and replace dangerous characters."""
    name = Path(original).name
    for ch in ("/", "\\", "\x00"):
        name = name.replace(ch, "_")
    return name or "upload"


class IngestController:
    """Controller for RAG data ingestion requests."""

    @staticmethod
    async def upload_file(
        file: UploadFile,
        source: str,
        author: str,
        current_admin,
    ) -> dict:
        """
        Validate, persist, and queue a file for RAG ingestion.

        Args:
            file: Uploaded file from request.
            source: Source label for document tracking.
            author: Author / data-owner label.
            current_admin: Authenticated admin user (tenant_id derived from JWT).

        Returns:
            dict with task_id, file name, size, and status.

        Raises:
            HTTPException 400: Unsupported file type.
            HTTPException 413: File exceeds the size limit.
            HTTPException 500: Unexpected server-side error.
        """
        tenant_id: str = str(current_admin.tenant_id)

        # Sanitise filename
        safe_name = _safe_filename(file.filename or "upload")
        file_ext = Path(safe_name).suffix.lower()

        # Validate extension
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"File type '{file_ext}' is not supported. "
                    f"Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
                ),
            )

        # End any stale MLflow run
        try:
            import mlflow

            mlflow.end_run()
        except Exception:
            pass

        mlflow_run_id = None

        try:
            upload_dir = Path("app/files/uploads")
            upload_dir.mkdir(parents=True, exist_ok=True)

            unique_name = f"{uuid.uuid4().hex}_{safe_name}"
            file_path = upload_dir / unique_name

            # Write in chunks, enforcing size limit
            total_bytes = 0
            with open(file_path, "wb") as buffer:
                while True:
                    chunk = await file.read(UPLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > MAX_FILE_SIZE_BYTES:
                        buffer.close()
                        file_path.unlink(missing_ok=True)
                        raise HTTPException(
                            status_code=413,
                            detail=(
                                f"File exceeds the maximum allowed size of "
                                f"{MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
                            ),
                        )
                    buffer.write(chunk)

            logger.info(
                f"File uploaded safely: original='{file.filename}' "
                f"stored='{unique_name}' size={total_bytes}B tenant={tenant_id}"
            )

            # MLflow tracking (lazy import to avoid pkg_resources at module load time)
            from app.services.mlflow_service import MLflowService

            mlflow_run_id = MLflowService.start_run(
                experiment_name=MLflowService.DEFAULT_EXPERIMENT_INGEST,
                run_name=f"ingest_{tenant_id}_{__import__('time').time()}",
                tags={
                    "tenant_id": tenant_id,
                    "admin_id": str(current_admin.id),
                    "uploaded_file": safe_name,
                },
            )
            if mlflow_run_id:
                import mlflow

                mlflow.log_param("tenant_id", tenant_id)
                mlflow.log_param("uploaded_file", safe_name)
                mlflow.log_param("source", source)
                mlflow.log_param("author", author)
                mlflow.log_metric("file_size_bytes", total_bytes)

            # Queue Celery task
            from app.services.rag_services.ingest_rag_service import ingest_file_task

            logger.info(f"Queuing ingest task: tenant={tenant_id} file={unique_name}")
            try:
                task = ingest_file_task.delay(
                    file_path=str(file_path),
                    tenant_id=tenant_id,
                    source=source,
                    author=author,
                )
                logger.info(f"✓ Task queued: {task.id}")
            except Exception as task_error:
                logger.error(
                    f"✗ Failed to queue ingest task: {type(task_error).__name__}: {task_error}",
                    exc_info=True,
                )
                raise

            logger.info(
                f"Ingestion queued — admin={current_admin.id} "
                f"tenant={tenant_id} file={safe_name} task={task.id}"
            )

            return {
                "message": "File processing task queued successfully",
                "task_id": task.id,
                "file": safe_name,
                "size_bytes": total_bytes,
                "status": "processing",
            }

        except HTTPException:
            raise
        except PermissionError as e:
            logger.error(f"Permission error during ingestion: {e}")
            raise HTTPException(
                status_code=403,
                detail="Server lacks permission to write the upload file.",
            )
        except ValueError as e:
            logger.error(f"Validation error during ingestion: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(
                f"Unexpected error during file ingestion: {type(e).__name__}: {e}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred while processing your file. Please try again later.",
            )
        finally:
            try:
                from app.services.mlflow_service import MLflowService

                MLflowService.end_run(status="FINISHED")
            except Exception as e:
                logger.error(f"Error ending MLflow run: {e}")
