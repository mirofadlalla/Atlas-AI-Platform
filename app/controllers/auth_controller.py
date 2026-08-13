"""
Authentication controller.

Centralises all authentication and user-management business logic so that
route handlers stay thin HTTP adapters.
"""

from sqlalchemy.orm import Session
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

    # ── Admin approval workflow ─────────────────────────────────────────────

    @staticmethod
    def get_pending_approvals(db: Session):
        from app.services.user_approval_service import UserApprovalService

        pending_users = UserApprovalService(db).get_pending_approvals()
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
