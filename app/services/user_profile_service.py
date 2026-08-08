"""Service for user profile management and retrieval."""

import logging
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class UserProfileService:
    """Service for user profile operations."""

    def __init__(self, db=None):
        self.db = db

    def get_profile(self, current_user):
        """
        Get current user's profile information.

        Args:
            current_user: Current authenticated user object

        Returns:
            Dictionary with user profile data

        Raises:
            HTTPException: If user not found or invalid
        """
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not authenticated",
            )

        try:
            profile_data = {
                "id": current_user.id,
                "name": current_user.name,
                "email": current_user.email,
                "tenant_id": current_user.tenant_id,
                "role": current_user.role,
                "approval_status": current_user.approval_status,
                "created_at": current_user.created_at,
            }
            return profile_data
        except Exception as e:
            logger.error(f"Error retrieving user profile: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve user profile",
            )
