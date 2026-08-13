"""
Routes for RAG data ingestion endpoints.

Thin HTTP adapter — all business logic lives in IngestController.
"""

import logging
from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.rate_limitizer import rate_limit
from app.services.auth_services.auth_service import require_admin
from app.controllers.ingest_rag_controller import IngestController

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest-rag")


@router.post("/upload_file")
async def upload_file(
    source: str = Form(...),
    author: str = Form(...),
    file: UploadFile = File(...),
    recursive: bool = Form(False),
    file_extensions: str = Form(None),
    current_admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Upload and ingest a file into the RAG system (admin only)."""
    rate_limit(
        user_id=str(current_admin.id), role="admin", endpoint="/ingest-rag/upload_file"
    )
    return await IngestController.upload_file(
        file=file,
        source=source,
        author=author,
        current_admin=current_admin,
    )
