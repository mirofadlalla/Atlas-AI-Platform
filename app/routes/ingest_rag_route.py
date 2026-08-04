"""
Routes for RAG data ingestion endpoints.

Implements admin-only access, rate limiting, and cost tracking for file ingestion.
"""
import logging
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.rate_limitizer import rate_limit
from app.services.mlflow_service import MLflowService
from app.services.rag_services.ingest_rag_service import ingest_file_task
from app.services.auth_services.auth_service import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/ingest-rag",
)

# ==================== FILE UPLOAD SECURITY CONSTANTS ====================

# Only these extensions are accepted for RAG ingestion.
ALLOWED_EXTENSIONS: set[str] = {
    ".pdf", ".txt", ".md", ".csv", ".docx", ".doc",
    ".pptx", ".ppt", ".xlsx", ".xls", ".html", ".json",
}

# Maximum permitted upload size: 50 MB
MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB

# How many bytes to read per chunk while writing to disk (avoids loading the
# entire file into memory for large uploads).
UPLOAD_CHUNK_SIZE: int = 1024 * 1024  # 1 MB


def _safe_filename(original: str) -> str:
    """
    Strip any directory components from a filename and replace potentially
    dangerous characters so the result is safe to use as a filesystem path.

    Examples::

        "../etc/passwd"   → "etc_passwd"
        "../../shell.sh"  → "shell.sh"
        "my file (1).pdf" → "my file (1).pdf"
    """
    # Take only the final component (guards against path traversal).
    name = Path(original).name
    # Replace any remaining path separators and null bytes that sneak through.
    for ch in ("/", "\\", "\x00"):
        name = name.replace(ch, "_")
    return name or "upload"


@router.post("/upload_file")
async def upload_file(
    source: str = Form(...),
    author: str = Form(...),
    file: UploadFile = File(...),
    recursive: bool = Form(False),
    file_extensions: str = Form(None),
    current_admin=Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Upload and ingest a file into the RAG system (admin only).

    Security hardening applied:
    - ``tenant_id`` is always taken from the authenticated admin's JWT — the
      client cannot supply or override it.
    - The filename is sanitised against path-traversal attacks.
    - Only files with an approved extension are accepted.
    - Files larger than 50 MB are rejected before touching disk.
    - Internal error details are never leaked to the HTTP response.

    Args:
        source: Source name for document tracking.
        author: Author / data-owner label.
        file: Uploaded file from the browser.
        recursive: Whether to process directories recursively (future use).
        file_extensions: Comma-separated additional extensions to recognise.
        current_admin: Authenticated admin user (JWT-derived — never trust client).
        db: Database session.

    Returns:
        Dictionary with ingestion task status and details.

    Raises:
        HTTPException 400: Unsupported file type.
        HTTPException 413: File exceeds the size limit.
        HTTPException 500: Unexpected server-side error (details hidden from client).
    """
    # ── Fix 2: derive tenant_id from JWT, never from the client ──────────────
    tenant_id: str = str(current_admin.tenant_id)

    # Apply role-aware rate limiting
    rate_limit(
        user_id=str(current_admin.id),
        role="admin",
        endpoint="/ingest-rag/upload_file"
    )

    # ── Fix 3a: sanitise filename ─────────────────────────────────────────────
    safe_name = _safe_filename(file.filename or "upload")
    file_ext = Path(safe_name).suffix.lower()

    # ── Fix 3b: validate file extension ──────────────────────────────────────
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type '{file_ext}' is not supported. "
                f"Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )

    # Always end any stale MLflow run from a previous request
    try:
        import mlflow
        mlflow.end_run()
    except Exception:
        pass

    mlflow_run_id = None

    try:
        upload_dir = Path("app/files/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Use a UUID prefix so two admins uploading the same filename never collide.
        unique_name = f"{uuid.uuid4().hex}_{safe_name}"
        file_path = upload_dir / unique_name

        # ── Fix 3c: enforce size limit while writing in chunks ────────────────
        total_bytes = 0
        with open(file_path, "wb") as buffer:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_FILE_SIZE_BYTES:
                    # Clean up the partially written file before raising
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

        # Start MLflow tracking run
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

        # Parse additional file extensions if provided
        file_ext_list = None
        if file_extensions:
            file_ext_list = [ext.strip() for ext in file_extensions.split(",")]

        # Queue the ingestion task to Celery
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
        # Re-raise validation / size errors unchanged so the client sees them.
        raise
    except PermissionError as e:
        logger.error(f"Permission error during ingestion: {e}")
        raise HTTPException(status_code=403, detail="Server lacks permission to write the upload file.")
    except ValueError as e:
        logger.error(f"Validation error during ingestion: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # ── Fix 4: never leak raw exception details to the client ─────────────
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
            MLflowService.end_run(status="FINISHED")
        except Exception as e:
            logger.error(f"Error ending MLflow run: {e}")