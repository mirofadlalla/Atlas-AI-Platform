"""
Routes for RAG evaluation and query endpoints.

Implements request logging, rate limiting, and cost tracking.
"""
from app.services.rag_services.eval_pipline import evaluate_task, generate_eval_dataset_task
from app.services.mlflow_service import MLflowService
from app.repositories.runs_repository import RunsRepository
from app.repositories.cost_log_repository import CostLogRepository
from app.core.rate_limitizer import rate_limit
from app.core.db import get_db
from app.services.auth_services.auth_service import require_admin

import logging
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from pathlib import Path
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/eval",
)


@router.post("/evaluate")
async def evaluate(
    tenant_id: str = Form(...),
    file: UploadFile = File(...),
    runs: int = Form(2),
    current_admin=Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Start an evaluation task (admin only).
    
    This endpoint:
    1. Verifies admin identity
    2. Applies rate limiting
    3. Logs the evaluation request
    4. Starts an MLflow run for tracking
    5. Submits evaluation task to Celery background worker
    
    Args:
        tenant_id: Tenant identifier
        file: Evaluation dataset file
        runs: Number of evaluation runs to perform
        current_user: Current user ID (from header/auth)
        user_role: Current user role (must be 'admin')
        db: Database session
        
    Returns:
        Dictionary with task ID and run ID
        
    Raises:
        HTTPException: If user is not admin
    """
    # Apply rate limiting (admin-only endpoint)
    rate_limit(
        user_id=str(current_admin.id),
        role="admin",
        endpoint="/eval/evaluate"
    )
    
    # Always end any active run from previous requests
    try:
        import mlflow
        mlflow.end_run()
    except:
        pass
    
    mlflow_run_id = None
    
    try:
        # Initialize MLflow experiment and start run
        mlflow_run_id = MLflowService.start_run(
            experiment_name=MLflowService.DEFAULT_EXPERIMENT_EVAL,
            run_name=f"eval_run_{tenant_id}_{int(__import__('time').time())}",
            tags={
                'tenant_id': tenant_id,
                'user_id': str(current_admin.id),
                'endpoint': '/eval/evaluate'
            }
        )
        
        # Log parameters only if run started successfully
        if mlflow_run_id:
            MLflowService.initialize_experiment(MLflowService.DEFAULT_EXPERIMENT_EVAL)
            import mlflow
            mlflow.log_param("tenant_id", tenant_id)
            mlflow.log_param("num_runs", runs)
            mlflow.log_param("dataset_filename", file.filename)
        
        # Save uploaded file
        upload_dir = Path("app/files/eval_files")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        temp_file_path = upload_dir / file.filename
        with open(temp_file_path, "wb") as buffer:
            buffer.write(await file.read())
        
        # Log artifact to MLflow
        mlflow.log_artifact(str(temp_file_path), artifact_path="evaluation_dataset")
        
        # Submit Celery task
        task = evaluate_task.delay(
            tenant_id=tenant_id,
            path=str(temp_file_path),
            runs=runs,
            run_id=mlflow_run_id
        )
        
        logger.info(
            f"Evaluation task started - Task ID: {task.id}, "
            f"Tenant: {tenant_id}, File: {file.filename}, Runs: {runs}"
        )
        
        return {
            "task_id": task.id,
            "run_id": mlflow_run_id,
            "status": "Evaluation started",
            "message": f"Evaluation task submitted successfully for {file.filename}"
        }
        
    except Exception as e:
        logger.error(f"Error starting evaluation: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        MLflowService.end_run(status="FINISHED")

@router.post("/generate_dataset")
async def generate_dataset(
    tenant_id: str = Form(...),
    max_chunks: int = Form(30),
    current_admin=Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Start a task to generate an evaluation dataset (admin only).
    """
    # Apply rate limiting
    rate_limit(
        user_id=str(current_admin.id),
        role="admin",
        endpoint="/eval/generate_dataset"
    )
    
    try:
        # Submit Celery task
        task = generate_eval_dataset_task.delay(
            tenant_id=tenant_id,
            max_chunks=max_chunks
        )
        
        logger.info(
            f"Dataset generation task started - Task ID: {task.id}, "
            f"Tenant: {tenant_id}, Max Chunks: {max_chunks}"
        )
        
        return {
            "task_id": task.id,
            "status": "Dataset generation started",
            "message": f"Dataset generation task submitted successfully."
        }
        
    except Exception as e:
        logger.error(f"Error starting dataset generation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{task_id}")
async def get_status(task_id: str):
    """
    Get the status of an evaluation task.
    
    Args:
        task_id: Celery task ID
        
    Returns:
        Dictionary with task status
    """
    try:
        from app.celery.celery_config import celery_app
        task_result = celery_app.AsyncResult(task_id)
        
        return {
            "task_id": task_id,
            "status": task_result.status,
            "result": task_result.result if task_result.status == 'SUCCESS' else None
        }
    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        raise HTTPException(status_code=500, detail=str(e))