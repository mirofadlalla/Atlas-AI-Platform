import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.auth_services.auth_service import get_current_user
from app.services.recommended_qa_service import RecommendedQAService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommended-qa", tags=["recommended-qa"])


class RecommendedQACreate(BaseModel):
    question: str = Field(..., min_length=1, description="Question text")
    answer: str = Field(..., min_length=1, description="Pre-defined answer text")


@router.get("")
async def get_recommended_questions(
    current_user=Depends(get_current_user), db: Session = Depends(get_db)
):
    """
    Get recommended questions and answers for current user's tenant from in-memory cache.
    Max 10 per tenant.
    """
    tenant_id = str(current_user.tenant_id)
    items = RecommendedQAService.get_recommended_questions(tenant_id, db)
    return {"tenant_id": tenant_id, "count": len(items), "recommended_qa": items}


@router.post("")
async def add_recommended_question(
    request: RecommendedQACreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Add a recommended question and answer pair for current tenant (Admin only).
    Enforces maximum of 10 items per tenant.
    """
    if getattr(current_user, "role", None) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only tenant admins can manage recommended questions.",
        )

    tenant_id = str(current_user.tenant_id)
    try:
        item = RecommendedQAService.add_recommended_question(
            tenant_id=tenant_id, question=request.question, answer=request.answer, db=db
        )
        return {
            "success": True,
            "message": "Recommended question added successfully",
            "item": item,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error(f"Error adding recommended QA: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add recommended question",
        )


@router.delete("/{qa_id}")
async def delete_recommended_question(
    qa_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)
):
    """
    Delete a recommended question and answer pair for current tenant (Admin only).
    """
    if getattr(current_user, "role", None) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only tenant admins can manage recommended questions.",
        )

    tenant_id = str(current_user.tenant_id)
    deleted = RecommendedQAService.delete_recommended_question(
        tenant_id=tenant_id, qa_id=qa_id, db=db
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recommended question not found for this tenant.",
        )

    return {"success": True, "message": "Recommended question deleted successfully"}
