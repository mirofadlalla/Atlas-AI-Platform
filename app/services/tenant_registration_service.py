"""Service for handling tenant registration and onboarding.

Registration flow
─────────────────
1. Caller submits organization name, admin email/password, and plan.
2. Tenant is created with status='pending'.
3. Admin user is created with approval_status='pending' and role='admin'.
4. NO access token is returned — the tenant cannot log in until a super
   admin approves the registration via PATCH /api/super-admin/tenants/{id}/approve.
5. When a super admin approves the tenant, both the tenant status and the
   admin user's approval_status are set to 'active'/'approved' in the same
   transaction, allowing the admin to log in and invite users.
"""

import logging
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.hash_service import password_hash
from app.schema.tenant_schema import (
    TenantRegistrationRequest,
    TenantRegistrationResponse,
)

logger = logging.getLogger(__name__)


class TenantRegistrationService:
    """Service for registering new tenants and their admin users."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db
        self.tenant_repo = TenantRepository(db)
        self.user_repo = UserRepository(db)

    def register_tenant(
        self, request: TenantRegistrationRequest
    ) -> TenantRegistrationResponse:
        """Register a new tenant with an admin user.

        The tenant and its admin are created with status/approval_status
        'pending'.  No JWT is issued.  The tenant cannot access the platform
        until a super admin approves the registration.

        Args:
            request: Tenant registration payload (org name, admin email/password, plan).

        Returns:
            TenantRegistrationResponse — no access_token field; message explains
            the pending state.

        Raises:
            HTTPException 409: If the organization name or email already exists.
            HTTPException 400: On any unexpected error.
        """
        try:
            # Check if tenant organization name already exists
            existing_tenant = self.tenant_repo.find_by_name(request.organization_name)
            if existing_tenant:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Organization '{request.organization_name}' already exists",
                )

            # Check if email already exists
            existing_user = self.user_repo.find_by_email(request.admin_email)
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already registered in system",
                )

            # Create tenant in 'pending' state — blocks all logins until approved.
            tenant = self.tenant_repo.create(
                name=request.organization_name,
                plan=request.plan,
                status="pending",
            )

            # Hash admin password
            hashed_password = password_hash(request.admin_password)

            # Create admin user in 'pending' state — cannot log in until both
            # the tenant is approved and the user's own approval_status is set
            # to 'approved' by a super admin.
            admin_user = self.user_repo.create(
                name=request.admin_name,
                email=request.admin_email,
                hashed_password=hashed_password,
                tenant_id=tenant.id,
                role="admin",
                approval_status="pending",
            )

            # Commit all changes
            self.tenant_repo.commit()

            logger.info(
                f"New tenant registration submitted (pending approval): "
                f"'{request.organization_name}' / admin: {request.admin_email}"
            )

            # Notify admin that the request is pending — no welcome email
            # yet because access has not been granted.
            try:
                from app.services.email_service import EmailService

                EmailService.send_pending_approval_email(
                    to_email=admin_user.email,
                    user_name=admin_user.name,
                    org_name=tenant.name,
                )
            except Exception as mail_err:
                logger.warning(
                    f"Failed to dispatch pending-approval email to "
                    f"{admin_user.email}: {mail_err}"
                )

            return TenantRegistrationResponse(
                tenant_id=tenant.id,
                admin_id=admin_user.id,
                organization_name=tenant.name,
                admin_email=admin_user.email,
                plan=tenant.plan,
                status=tenant.status,
                message=(
                    f"Registration for '{request.organization_name}' has been submitted "
                    f"and is awaiting super admin approval. You will receive an email "
                    f"once access is granted."
                ),
            )

        except HTTPException:
            self.tenant_repo.rollback()
            raise
        except Exception as e:
            self.tenant_repo.rollback()
            logger.error(f"Error registering tenant: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error registering tenant: {str(e)}",
            )
