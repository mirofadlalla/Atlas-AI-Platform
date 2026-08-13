"""
Routes for RAG evaluation and dataset generation endpoints.

Thin HTTP adapter — all business logic lives in EvalController.
"""

import logging
from fastapi import APIRouter, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.rate_limitizer import rate_limit
from app.services.auth_services.auth_service import require_admin
from app.controllers.eval_controller import EvalController

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/eval")


@router.post("/evaluate")
async def evaluate(
    file: UploadFile = File(...),
    runs: int = Form(2),
    current_admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Start a RAG evaluation task (admin only)."""
    rate_limit(user_id=str(current_admin.id), role="admin", endpoint="/eval/evaluate")
    return await EvalController.evaluate(file, runs, current_admin)


@router.post("/generate_dataset")
async def generate_dataset(
    max_chunks: int = Form(30),
    current_admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Start a task to auto-generate an evaluation dataset (admin only)."""
    rate_limit(
        user_id=str(current_admin.id), role="admin", endpoint="/eval/generate_dataset"
    )
    return EvalController.generate_dataset(max_chunks, current_admin)


@router.get("/status/{task_id}")
async def get_status(task_id: str):
    """Get the status of an evaluation or dataset-generation Celery task."""
    return EvalController.get_status(task_id)
