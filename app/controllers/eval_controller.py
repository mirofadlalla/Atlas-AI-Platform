"""
Eval controller.

Centralises evaluation pipeline orchestration: MLflow tracking, Celery task
submission, dataset generation, and status polling.
"""

import logging
from pathlib import Path

from fastapi import HTTPException, UploadFile

# MLflowService imported lazily inside methods to avoid pulling mlflow
# (and its pkg_resources dep) at module import time — breaks CI environments.

logger = logging.getLogger(__name__)


class EvalController:
    """Controller for all /eval endpoints."""

    # ── /eval/evaluate ────────────────────────────────────────────────────────

    @staticmethod
    async def evaluate(file: UploadFile, runs: int, current_admin) -> dict:
        """
        Start a RAG evaluation task.

        Uploads the dataset file, logs to MLflow, and submits a Celery task.
        """
        from app.services.rag_services.eval_pipline import evaluate_task
        from app.services.mlflow_service import MLflowService

        tenant_id = str(current_admin.tenant_id)

        # End any stale MLflow run
        try:
            import mlflow

            mlflow.end_run()
        except Exception:
            pass

        mlflow_run_id = None

        try:
            mlflow_run_id = MLflowService.start_run(
                experiment_name=MLflowService.DEFAULT_EXPERIMENT_EVAL,
                run_name=f"eval_run_{tenant_id}_{int(__import__('time').time())}",
                tags={
                    "tenant_id": tenant_id,
                    "user_id": str(current_admin.id),
                    "endpoint": "/eval/evaluate",
                },
            )

            if mlflow_run_id:
                MLflowService.initialize_experiment(
                    MLflowService.DEFAULT_EXPERIMENT_EVAL
                )
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

            mlflow.log_artifact(str(temp_file_path), artifact_path="evaluation_dataset")

            # Submit Celery task
            task = evaluate_task.delay(
                tenant_id=tenant_id,
                path=str(temp_file_path),
                runs=runs,
                run_id=mlflow_run_id,
            )

            logger.info(
                f"Evaluation task started - Task ID: {task.id}, "
                f"Tenant: {tenant_id}, File: {file.filename}, Runs: {runs}"
            )

            return {
                "task_id": task.id,
                "run_id": mlflow_run_id,
                "status": "Evaluation started",
                "message": f"Evaluation task submitted successfully for {file.filename}",
            }

        except Exception as e:
            logger.error(f"Error starting evaluation: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred while starting the evaluation. Please try again.",
            )
        finally:
            try:
                from app.services.mlflow_service import MLflowService

                MLflowService.end_run(status="FINISHED")
            except Exception as e:
                logger.error(f"Error ending MLflow run: {e}")

    # ── /eval/generate_dataset ────────────────────────────────────────────────

    @staticmethod
    def generate_dataset(max_chunks: int, current_admin) -> dict:
        """Submit a Celery task to auto-generate an evaluation dataset."""
        from app.services.rag_services.eval_pipline import generate_eval_dataset_task

        tenant_id = str(current_admin.tenant_id)

        try:
            task = generate_eval_dataset_task.delay(
                tenant_id=tenant_id, max_chunks=max_chunks
            )
            logger.info(
                f"Dataset generation task started - Task ID: {task.id}, "
                f"Tenant: {tenant_id}, Max Chunks: {max_chunks}"
            )
            return {
                "task_id": task.id,
                "status": "Dataset generation started",
                "message": "Dataset generation task submitted successfully.",
            }
        except Exception as e:
            logger.error(f"Error starting dataset generation: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred while starting dataset generation. Please try again.",
            )

    # ── /eval/status/{task_id} ────────────────────────────────────────────────

    @staticmethod
    def get_status(task_id: str) -> dict:
        """Return the current Celery task status."""
        try:
            from app.celery.celery_config import celery_app

            task_result = celery_app.AsyncResult(task_id)
            return {
                "task_id": task_id,
                "status": task_result.status,
                "result": (
                    task_result.result if task_result.status == "SUCCESS" else None
                ),
            }
        except Exception as e:
            logger.error(f"Error getting task status: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred while retrieving task status. Please try again.",
            )
