"""
Routes for RAG data ingestion endpoints.

Implements admin-only access, rate limiting, and cost tracking for file ingestion.
"""
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.rate_limitizer import rate_limit
from app.services.rag_services.path_processing_service import PathProcessingService
from app.services.mlflow_service import MLflowService
from app.services.rag_services.ingest_rag_service import ingest_file_task
from app.services.auth_services.auth_service import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/ingest-rag",
)


@router.post("/upload_file")
async def upload_file(
    tenant_id: str = Form(...),
    source: str = Form(...),
    author: str = Form(...),
    file: UploadFile = File(...),
    recursive: bool = Form(False),
    file_extensions: str = Form(None),
    current_admin=Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Upload and ingest a file into the RAG system.
    
    This endpoint:
    1. Accepts file upload from browser
    2. Saves uploaded file to server storage
    3. Applies rate limiting (admin-specific)
    4. Verifies admin identity
    5. Logs ingestion metrics to MLflow
    6. Processes file and ingests into vector database
    
    Args:
        tenant_id: Tenant identifier
        source: Source name for tracking
        author: Author name
        file: Uploaded file from browser
        recursive: Whether to process directories recursively
        file_extensions: Comma-separated file extensions to process
        current_admin: Authenticated admin user (from JWT)
        user_role: Current user role (must be 'admin')
        db: Database session
        
    Returns:
        Dictionary with ingestion status and details
        
    Raises:
        HTTPException: If user is not admin or other validation fails
    """
    # Apply rate limiting (admin-only endpoint)
    rate_limit(
        user_id=str(current_admin.id),
        role="admin",
        endpoint="/ingest-rag/upload_file"
    )
    
    # Always end any active run from previous requests
    try:
        import mlflow
        mlflow.end_run()
    except:
        pass
    
    mlflow_run_id = None
    
    try:
        # Create upload directory
        upload_dir = Path("app/files/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Save uploaded file
        file_path = upload_dir / file.filename
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
        
        logger.info(f"File uploaded: {file.filename} -> {file_path}")
        
        # Log ingestion start to MLflow
        mlflow_run_id = MLflowService.start_run(
            experiment_name=MLflowService.DEFAULT_EXPERIMENT_INGEST,
            run_name=f"ingest_{tenant_id}_{__import__('time').time()}",
            tags={
                'tenant_id': tenant_id,
                'admin_id': str(current_admin.id),
                'uploaded_file': file.filename
            }
        )
        
        # Log parameters only if run started successfully
        if mlflow_run_id:
            import mlflow
            mlflow.log_param("tenant_id", tenant_id)
            mlflow.log_param("uploaded_file", file.filename)
            mlflow.log_param("source", source)
            mlflow.log_param("author", author)
        
        # Parse file extensions if provided
        file_ext_list = None
        if file_extensions:
            file_ext_list = [ext.strip() for ext in file_extensions.split(",")]
        
        # Send file processing task to Celery queue (async)
        logger.info(f"Attempting to queue task: tenant_id={tenant_id}, file={file.filename}")
        
        try:
            task = ingest_file_task.delay(
                file_path=str(file_path),
                tenant_id=tenant_id,  # Keep as string (UUID)
                source=source,
                author=author
            )
            logger.info(f"✓ Task queued successfully: {task.id}")
        except Exception as task_error:
            logger.error(f"✗ Failed to queue task: {type(task_error).__name__}: {task_error}", exc_info=True)
            raise
        
        logger.info(
            f"File ingestion task queued - Admin: {current_admin.id}, "
            f"Tenant: {tenant_id}, File: {file.filename}, Task ID: {task.id}"
        )
        
        return {
            "message": "File processing task queued successfully",
            "task_id": task.id,
            "file": file.filename,
            "status": "processing"
        }
        
    except PermissionError as e:
        logger.error(f"Permission error during ingestion: {e}")
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        logger.error(f"Validation error during ingestion: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error during file ingestion: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            MLflowService.end_run(status="FINISHED")
        except Exception as e:
            logger.error(f"Error ending MLflow run: {e}")