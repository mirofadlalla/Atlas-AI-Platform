"""
Super Admin Service.

Contains all business logic for the super admin dashboard:
  - Platform-wide statistics
  - Tenant CRUD operations
  - Cross-tenant user management
  - Super admin account bootstrap
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.schema.super_admin_schema import (
    CreateSuperAdminRequest,
    SuperAdminStatsResponse,
    TenantDetailResponse,
    TenantSummary,
    UpdateTenantRequest,
    UserSummary,
)
from app.services.hash_service import password_hash


class SuperAdminService:
    """Service layer for all super admin operations.

    Super admin users have ``tenant_id = None`` — they exist outside any
    tenant and have unrestricted read/write access across the whole platform.
    """

    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.tenant_repo = TenantRepository(db)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _tenant_summary(self, tenant) -> TenantSummary:
        """Build a TenantSummary DTO for the given ORM tenant object."""
        user_count = self.user_repo.count_by_tenant(str(tenant.id))
        return TenantSummary(
            id=str(tenant.id),
            name=tenant.name,
            plan=tenant.plan,
            status=tenant.status,
            created_at=tenant.created_at,
            user_count=user_count,
        )

    @staticmethod
    def _user_summary(user) -> UserSummary:
        """Build a UserSummary DTO for the given ORM user object."""
        return UserSummary(
            id=str(user.id),
            name=user.name,
            email=user.email,
            role=user.role,
            approval_status=user.approval_status,
            created_at=user.created_at,
            tenant_id=str(user.tenant_id) if user.tenant_id else None,
        )

    # ── Dashboard ─────────────────────────────────────────────────────────────

    def get_dashboard_stats(self) -> SuperAdminStatsResponse:
        """Return platform-level statistics including pending tenant count."""
        tenants = self.tenant_repo.find_all()
        total_users = len(self.user_repo.find_all())
        pending = [t for t in tenants if t.status == "pending"]
        return SuperAdminStatsResponse(
            total_tenants=len(tenants),
            total_users=total_users,
            pending_tenants=len(pending),
            tenants=[self._tenant_summary(t) for t in tenants],
        )

    # ── Tenants ───────────────────────────────────────────────────────────────

    def get_all_tenants(self) -> list[TenantSummary]:
        """Return all tenants with their current user counts."""
        tenants = self.tenant_repo.find_all()
        return [self._tenant_summary(t) for t in tenants]

    def get_pending_tenants(self) -> list[TenantSummary]:
        """Return only tenants awaiting super admin approval."""
        tenants = self.tenant_repo.find_all_by_status("pending")
        return [self._tenant_summary(t) for t in tenants]

    def approve_tenant(self, tenant_id: str) -> TenantDetailResponse:
        """Approve a pending tenant registration.

        Atomically sets:
          - tenant.status       → 'active'
          - every user in the tenant whose approval_status is 'pending'
            → 'approved'   (so the admin can log in immediately)

        Args:
            tenant_id: UUID of the tenant to approve.

        Raises:
            HTTPException 404: Tenant not found.
            HTTPException 400: Tenant is not in 'pending' state.
        """
        tenant = self.tenant_repo.find_by_id(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant '{tenant_id}' not found.",
            )
        if tenant.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Tenant is already '{tenant.status}'. "
                    "Only 'pending' tenants can be approved."
                ),
            )

        # Activate the tenant
        self.tenant_repo.update_status(tenant_id, "active")

        # Approve every pending user in that tenant so the admin can log in.
        users = self.user_repo.find_all_by_tenant(tenant_id)
        for user in users:
            if user.approval_status == "pending":
                self.user_repo.update_approval_status(str(user.id), "approved")

        self.tenant_repo.commit()

        # Re-fetch so the response reflects the committed state.
        tenant = self.tenant_repo.find_by_id(tenant_id)
        users = self.user_repo.find_all_by_tenant(tenant_id)

        # Fire approval email to admin(s) — non-fatal if it fails
        try:
            from app.services.email_service import EmailService

            for user in users:
                if user.role == "admin":
                    EmailService.send_tenant_approved_email(
                        to_email=user.email,
                        user_name=user.name,
                        org_name=tenant.name,
                    )
        except Exception as mail_err:
            import logging

            logging.getLogger(__name__).warning(
                f"Approval email failed for tenant {tenant_id}: {mail_err}"
            )

        return TenantDetailResponse(
            tenant=self._tenant_summary(tenant),
            users=[self._user_summary(u) for u in users],
        )

    def reject_tenant(self, tenant_id: str, reason: str) -> TenantDetailResponse:
        """Reject a pending tenant registration.

        Sets tenant.status → 'rejected' and every pending user's
        approval_status → 'rejected', permanently blocking login.

        Args:
            tenant_id: UUID of the tenant to reject.
            reason:    Human-readable reason sent to the tenant admin.

        Raises:
            HTTPException 404: Tenant not found.
            HTTPException 400: Tenant is not in 'pending' state.
        """
        tenant = self.tenant_repo.find_by_id(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant '{tenant_id}' not found.",
            )
        if tenant.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Tenant is already '{tenant.status}'. "
                    "Only 'pending' tenants can be rejected."
                ),
            )

        self.tenant_repo.update_status(tenant_id, "rejected")

        users = self.user_repo.find_all_by_tenant(tenant_id)
        for user in users:
            if user.approval_status == "pending":
                self.user_repo.update_approval_status(str(user.id), "rejected")

        self.tenant_repo.commit()

        tenant = self.tenant_repo.find_by_id(tenant_id)
        users = self.user_repo.find_all_by_tenant(tenant_id)

        try:
            from app.services.email_service import EmailService

            for user in users:
                if user.role == "admin":
                    EmailService.send_tenant_rejected_email(
                        to_email=user.email,
                        user_name=user.name,
                        org_name=tenant.name,
                        reason=reason,
                    )
        except Exception as mail_err:
            import logging

            logging.getLogger(__name__).warning(
                f"Rejection email failed for tenant {tenant_id}: {mail_err}"
            )

        return TenantDetailResponse(
            tenant=self._tenant_summary(tenant),
            users=[self._user_summary(u) for u in users],
        )

    def get_tenant_detail(self, tenant_id: str) -> TenantDetailResponse:
        """Return a single tenant and the full list of its users.

        Raises:
            HTTPException: 404 if the tenant does not exist.
        """
        tenant = self.tenant_repo.find_by_id(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant '{tenant_id}' not found.",
            )
        users = self.user_repo.find_all_by_tenant(tenant_id)
        return TenantDetailResponse(
            tenant=self._tenant_summary(tenant),
            users=[self._user_summary(u) for u in users],
        )

    def delete_tenant(self, tenant_id: str) -> dict:
        """Delete a tenant and all of its users (cascade).

        Args:
            tenant_id: UUID of the tenant to remove.

        Raises:
            HTTPException: 404 if the tenant does not exist.
        """
        tenant = self.tenant_repo.find_by_id(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant '{tenant_id}' not found.",
            )

        # Delete all users in the tenant first to maintain referential integrity.
        users = self.user_repo.find_all_by_tenant(tenant_id)
        for user in users:
            self.user_repo.delete(str(user.id))

        self.tenant_repo.delete(tenant_id)
        self.tenant_repo.commit()
        return {"status": "deleted", "tenant_id": tenant_id}

    def update_tenant(
        self, tenant_id: str, request: UpdateTenantRequest
    ) -> TenantSummary:
        """Update a tenant's name and/or plan.

        Args:
            tenant_id: UUID of the tenant to update.
            request: Partial update payload (name, plan — both optional).

        Raises:
            HTTPException: 404 if the tenant does not exist.
        """
        tenant = self.tenant_repo.update(
            tenant_id, name=request.name, plan=request.plan
        )
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant '{tenant_id}' not found.",
            )
        self.tenant_repo.commit()
        return self._tenant_summary(tenant)

    # ── Users ─────────────────────────────────────────────────────────────────

    def get_all_users(self) -> list[UserSummary]:
        """Return every user across all tenants."""
        users = self.user_repo.find_all()
        return [self._user_summary(u) for u in users]

    def get_tenant_users(self, tenant_id: str) -> list[UserSummary]:
        """Return all users scoped to a specific tenant.

        Raises:
            HTTPException: 404 if the tenant does not exist.
        """
        if not self.tenant_repo.find_by_id(tenant_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant '{tenant_id}' not found.",
            )
        users = self.user_repo.find_all_by_tenant(tenant_id)
        return [self._user_summary(u) for u in users]

    def delete_user(self, user_id: str, requester_id: str) -> dict:
        """Delete a user by ID.

        Args:
            user_id: UUID of the user to remove.
            requester_id: UUID of the caller (to prevent self-deletion).

        Raises:
            HTTPException: 403 if the caller attempts to delete their own account.
            HTTPException: 404 if the user does not exist.
        """
        if str(user_id) == str(requester_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot delete your own account.",
            )
        user = self.user_repo.find_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{user_id}' not found.",
            )
        self.user_repo.delete(user_id)
        self.user_repo.commit()
        return {"status": "deleted", "user_id": user_id}

    def update_user_role(self, user_id: str, role: str) -> UserSummary:
        """Change a user's role.

        Args:
            user_id: UUID of the target user.
            role: New role — must be one of 'user', 'admin', 'super_admin'.

        Raises:
            HTTPException: 400 for an unrecognised role value.
            HTTPException: 404 if the user does not exist.
        """
        valid_roles = {"user", "admin", "super_admin"}
        if role not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role '{role}'. Must be one of: {', '.join(sorted(valid_roles))}.",
            )
        user = self.user_repo.update_role(user_id, role)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{user_id}' not found.",
            )
        self.user_repo.commit()
        return self._user_summary(user)

    def update_user_status(self, user_id: str, approval_status: str) -> UserSummary:
        """Change a user's approval status.

        Args:
            user_id: UUID of the target user.
            approval_status: New status — must be one of 'approved', 'pending', 'rejected'.

        Raises:
            HTTPException: 400 for an unrecognised status value.
            HTTPException: 404 if the user does not exist.
        """
        valid_statuses = {"approved", "pending", "rejected"}
        if approval_status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid status '{approval_status}'. "
                    f"Must be one of: {', '.join(sorted(valid_statuses))}."
                ),
            )
        user = self.user_repo.update_approval_status(user_id, approval_status)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{user_id}' not found.",
            )
        self.user_repo.commit()
        return self._user_summary(user)

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    def create_super_admin(
        self, request: CreateSuperAdminRequest, secret_key_from_env: str
    ) -> UserSummary:
        """Bootstrap the first super admin account.

        Validates the provided ``secret_key`` against the environment variable
        ``SUPER_ADMIN_SECRET_KEY`` before creating the account.  The created user
        has ``tenant_id = None`` and ``approval_status = 'approved'``.

        Args:
            request: Registration payload including the secret key.
            secret_key_from_env: The value of ``SUPER_ADMIN_SECRET_KEY`` read
                                 from the environment by the caller.

        Raises:
            HTTPException: 403 if the secret key is missing or incorrect.
            HTTPException: 400 if the email address is already registered.
        """
        if not secret_key_from_env or request.secret_key != secret_key_from_env:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or missing super admin secret key.",
            )

        existing = self.user_repo.find_by_email(request.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered.",
            )

        hashed = password_hash(request.password)
        user = self.user_repo.create(
            name=request.name,
            email=request.email,
            hashed_password=hashed,
            tenant_id=None,
            role="super_admin",
            approval_status="approved",
        )
        self.user_repo.commit()
        return self._user_summary(user)
