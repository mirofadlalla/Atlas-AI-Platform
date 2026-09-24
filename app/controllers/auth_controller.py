"""
Authentication controller.

Centralises all authentication and user-management business logic so that
route handlers stay thin HTTP adapters.
"""

from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.services.auth_services.auth_admin_service import AuthService
from app.schema.auth_admin import UserCreate, UserLogin


class AuthController:
    # ── Basic auth ──────────────────────────────────────────────────────────

    @staticmethod
    def register(user_data: UserCreate, db: Session):
        service = AuthService(db)
        return service.register_user(user_data)

    @staticmethod
    def login(user_data: UserLogin, db: Session):
        service = AuthService(db)
        return service.login_user(user_data.email, user_data.password)

    @staticmethod
    def get_profile(current_user):
        from app.services.user_profile_service import UserProfileService

        return UserProfileService().get_profile(current_user)

    # ── Tenant registration ─────────────────────────────────────────────────

    @staticmethod
    def register_tenant(request, db: Session):
        from app.services.tenant_registration_service import TenantRegistrationService

        return TenantRegistrationService(db).register_tenant(request)

    # ── Invitation management ───────────────────────────────────────────────

    @staticmethod
    def send_invitation(
        invited_email: str, invited_by_id, tenant_id: str, admin_id, db: Session
    ):
        from app.services.invitation_management_service import (
            InvitationManagementService,
        )

        return InvitationManagementService(db).send_invitation(
            invited_email=invited_email,
            invited_by_id=invited_by_id,
            tenant_id=tenant_id,
            admin_id=admin_id,
        )

    @staticmethod
    def validate_invitation(token: str, db: Session):
        from app.services.invitation_management_service import (
            InvitationManagementService,
        )

        return InvitationManagementService(db).validate_invitation(token)

    @staticmethod
    def register_via_invitation(
        token: str, name: str, password: str, tenant_id: str, db: Session
    ):
        from app.services.invitation_management_service import (
            InvitationManagementService,
        )

        return InvitationManagementService(db).register_via_invitation(
            token=token,
            name=name,
            password=password,
            tenant_id=tenant_id,
        )

    @staticmethod
    def get_pending_invitations(admin_id, db: Session):
        from app.services.invitation_management_service import (
            InvitationManagementService,
        )

        return InvitationManagementService(db).get_pending_invitations(admin_id)

    @staticmethod
    def resend_invitation(token: str, db: Session):
        from app.services.invitation_management_service import (
            InvitationManagementService,
        )

        return InvitationManagementService(db).resend_invitation(token)

    @staticmethod
    def delete_invitation(invitation_id: str, tenant_id: str, db: Session):
        from app.repositories.invitation_repository import InvitationRepository

        invitation = InvitationRepository(db).get_by_id(invitation_id)
        # Tenant admins may revoke any invitation in their own tenant, even if
        # another tenant admin originally created it.
        if not invitation or str(invitation.tenant_id) != str(tenant_id):
            raise HTTPException(status_code=404, detail="Invitation not found")
        InvitationRepository(db).delete(invitation_id)
        return {"status": "deleted"}

    # ── Admin approval workflow ─────────────────────────────────────────────

    @staticmethod
    def get_pending_approvals(tenant_id: str, db: Session):
        from app.services.user_approval_service import UserApprovalService

        pending_users = UserApprovalService(db).get_pending_approvals(str(tenant_id))
        return {
            "total": len(pending_users),
            "pending_users": [
                {
                    "user_id": u.id,
                    "name": u.name,
                    "email": u.email,
                    "created_at": u.created_at,
                }
                for u in pending_users
            ],
        }

    @staticmethod
    def approve_user(user_id: str, admin_id, db: Session):
        from app.services.user_approval_service import UserApprovalService

        return UserApprovalService(db).approve_user(user_id, admin_id)

    @staticmethod
    def reject_user(user_id: str, admin_id, db: Session):
        from app.services.user_approval_service import UserApprovalService

        return UserApprovalService(db).reject_user(user_id, admin_id)

    # ── Admin — Tenant-scoped User Management ──────────────────────────────

    @staticmethod
    def admin_list_users(tenant_id: str, db: Session):
        """List all users in the admin's own tenant."""
        from app.services.super_admin_service import SuperAdminService

        service = SuperAdminService(db)
        return service.get_tenant_users(tenant_id)

    @staticmethod
    def admin_delete_user(user_id: str, requester_id: str, tenant_id: str, db: Session):
        """Delete a user from the admin's tenant.

        Guards:
        - Cannot delete self.
        - Target user must belong to the same tenant.
        """
        from app.repositories.user_repository import UserRepository
        from app.services.super_admin_service import SuperAdminService

        # Verify the target user belongs to the admin's tenant.
        user_repo = UserRepository(db)
        target = user_repo.find_by_id(user_id)
        if not target or str(target.tenant_id) != str(tenant_id):
            raise HTTPException(
                status_code=404, detail="User not found in your tenant."
            )

        return SuperAdminService(db).delete_user(user_id, requester_id)

    @staticmethod
    def admin_update_user_role(
        user_id: str, role: str, requester_tenant_id: str, db: Session
    ):
        """Update a user's role, scoped to the admin's tenant.

        Guards:
        - Target user must belong to the same tenant.
        - Cannot change the role of a super_admin.
        """
        from app.repositories.user_repository import UserRepository
        from app.services.super_admin_service import SuperAdminService

        user_repo = UserRepository(db)
        target = user_repo.find_by_id(user_id)
        if not target or str(target.tenant_id) != str(requester_tenant_id):
            raise HTTPException(
                status_code=404, detail="User not found in your tenant."
            )
        if target.role == "super_admin":
            raise HTTPException(
                status_code=403,
                detail="Cannot change the role of a super admin.",
            )

        return SuperAdminService(db).update_user_role(user_id, role)

    @staticmethod
    def admin_update_user_status(
        user_id: str, approval_status: str, requester_tenant_id: str, db: Session
    ):
        """Update a user's approval status, scoped to the admin's tenant.

        Guards:
        - Target user must belong to the same tenant.
        """
        from app.repositories.user_repository import UserRepository
        from app.services.super_admin_service import SuperAdminService

        user_repo = UserRepository(db)
        target = user_repo.find_by_id(user_id)
        if not target or str(target.tenant_id) != str(requester_tenant_id):
            raise HTTPException(
                status_code=404, detail="User not found in your tenant."
            )

        return SuperAdminService(db).update_user_status(user_id, approval_status)
