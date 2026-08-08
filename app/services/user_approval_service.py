"""Service for user approval workflow management."""

import logging
from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class UserApprovalService:
    """Service for managing user approval workflow."""

    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)

    def authorize_admin(self, user_role: str, action: str) -> None:
        """
        Verify that the user has admin role.

        Args:
            user_role: Role of current user
            action: Action being performed (for logging)

        Raises:
            HTTPException: If user is not admin
        """
        if user_role != "admin":
            logger.warning(f"Unauthorized {action} attempt by non-admin user")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can perform this action",
            )

    def get_pending_approvals(self) -> list:
        """
        Get all users pending approval.

        Returns:
            List of pending users

        Raises:
            HTTPException: On database error
        """
        try:
            from app.models.user import Users

            pending_users = (
                self.db.query(Users).filter(Users.approval_status == "pending").all()
            )
            return pending_users
        except Exception as e:
            logger.error(f"Error retrieving pending approvals: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve pending approvals",
            )

    def approve_user(self, user_id: str, current_user_id: str) -> dict:
        """
        Approve a pending user registration.

        Args:
            user_id: ID of user to approve
            current_user_id: ID of admin performing approval

        Returns:
            Updated user data

        Raises:
            HTTPException: If user not found or not pending
        """
        try:
            user = self.user_repo.find_by_id(user_id)

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
                )

            if user.approval_status != "pending":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User is already {user.approval_status}",
                )

            user.approval_status = "approved"
            user.approved_by = current_user_id
            user.approved_at = datetime.utcnow()

            self.user_repo.commit()

            logger.info(f"User {user.email} approved by admin {current_user_id}")

            # Send approval notification email
            try:
                from app.services.email_service import EmailService

                EmailService.send_approval_status_email(
                    user.email, user.name, "approved"
                )
            except Exception as mail_err:
                logger.error(
                    f"Failed to dispatch approval email to {user.email}: {mail_err}"
                )

            return {
                "user_id": user.id,
                "email": user.email,
                "name": user.name,
                "approval_status": user.approval_status,
                "approved_at": user.approved_at,
                "message": "User approved successfully",
            }
        except HTTPException:
            self.user_repo.rollback()
            raise
        except Exception as e:
            self.user_repo.rollback()
            logger.error(f"Error approving user: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to approve user",
            )

    def reject_user(self, user_id: str, current_user_id: str) -> dict:
        """
        Reject a pending user registration.

        Args:
            user_id: ID of user to reject
            current_user_id: ID of admin performing rejection

        Returns:
            Updated user data

        Raises:
            HTTPException: If user not found or not pending
        """
        try:
            user = self.user_repo.find_by_id(user_id)

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
                )

            if user.approval_status != "pending":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot reject user with status: {user.approval_status}",
                )

            user.approval_status = "rejected"
            user.approved_by = current_user_id
            user.approved_at = datetime.utcnow()

            self.user_repo.commit()

            logger.info(f"User {user.email} rejected by admin {current_user_id}")

            # Send rejection notification email
            try:
                from app.services.email_service import EmailService

                EmailService.send_approval_status_email(
                    user.email, user.name, "rejected"
                )
            except Exception as mail_err:
                logger.error(
                    f"Failed to dispatch rejection email to {user.email}: {mail_err}"
                )

            return {
                "user_id": user.id,
                "email": user.email,
                "name": user.name,
                "approval_status": user.approval_status,
                "rejected_at": user.approved_at,
                "message": "User rejected successfully",
            }
        except HTTPException:
            self.user_repo.rollback()
            raise
        except Exception as e:
            self.user_repo.rollback()
            logger.error(f"Error rejecting user: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reject user",
            )
