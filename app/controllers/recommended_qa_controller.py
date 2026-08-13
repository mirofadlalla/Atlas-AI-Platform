"""
Recommended QA controller.

Manages the recommended questions and answers per tenant: listing,
adding (admin only), and deleting (admin only).
"""

import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.services.recommended_qa_service import RecommendedQAService

logger = logging.getLogger(__name__)


class RecommendedQAController:
    """Controller for all /recommended-qa endpoints."""

    @staticmethod
    def get_recommended_questions(current_user, db: Session) -> dict:
        """Return all recommended QA pairs for the current tenant (max 10)."""
        tenant_id = str(current_user.tenant_id)
        items = RecommendedQAService.get_recommended_questions(tenant_id, db)
        return {"tenant_id": tenant_id, "count": len(items), "recommended_qa": items}

    @staticmethod
    def add_recommended_question(request, current_user, db: Session) -> dict:
        """
        Add a recommended QA pair for the current tenant (admin only).

        Raises:
            HTTPException 403: If caller is not an admin.
            HTTPException 400: If business validation fails (e.g. limit reached).
            HTTPException 500: On unexpected errors.
        """
        if getattr(current_user, "role", None) != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only tenant admins can manage recommended questions.",
            )

        tenant_id = str(current_user.tenant_id)
        try:
            item = RecommendedQAService.add_recommended_question(
                tenant_id=tenant_id,
                question=request.question,
                answer=request.answer,
                db=db,
            )
            return {
                "success": True,
                "message": "Recommended question added successfully",
                "item": item,
            }
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            )
        except Exception as exc:
            logger.error(f"Error adding recommended QA: {exc}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to add recommended question",
            )

    @staticmethod
    def delete_recommended_question(qa_id: str, current_user, db: Session) -> dict:
        """
        Delete a recommended QA pair (admin only).

        Raises:
            HTTPException 403: If caller is not an admin.
            HTTPException 404: If the QA pair is not found.
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
