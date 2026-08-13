"""
Routes for recommended QA management.

Thin HTTP adapter — all business logic lives in RecommendedQAController.
"""

import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.auth_services.auth_service import get_current_user
from app.controllers.recommended_qa_controller import RecommendedQAController

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommended-qa", tags=["recommended-qa"])


class RecommendedQACreate(BaseModel):
    question: str = Field(..., min_length=1, description="Question text")
    answer: str = Field(..., min_length=1, description="Pre-defined answer text")


@router.get("")
async def get_recommended_questions(
    current_user=Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get recommended questions and answers for the current tenant (max 10)."""
    return RecommendedQAController.get_recommended_questions(current_user, db)


@router.post("")
async def add_recommended_question(
    request: RecommendedQACreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a recommended QA pair for the current tenant (admin only, max 10)."""
    return RecommendedQAController.add_recommended_question(request, current_user, db)


@router.delete("/{qa_id}")
async def delete_recommended_question(
    qa_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)
):
    """Delete a recommended QA pair for the current tenant (admin only)."""
    return RecommendedQAController.delete_recommended_question(qa_id, current_user, db)
