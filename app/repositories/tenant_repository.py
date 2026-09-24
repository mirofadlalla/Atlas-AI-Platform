from sqlalchemy.orm import Session
from app.models.tenant import Tenants


class TenantRepository:
    """Repository for Tenant database operations."""

    def __init__(self, db: Session):
        self.db = db

    def find_by_name(self, name: str):
        """Find tenant by organization name."""
        return self.db.query(Tenants).filter(Tenants.name == name).first()

    def find_by_id(self, tenant_id: str):
        """Find tenant by ID."""
        return self.db.query(Tenants).filter(Tenants.id == tenant_id).first()

    def create(self, name: str, plan: str = "starter", status: str = "pending"):
        """Create a new tenant.

        Args:
            name:   Organization name.
            plan:   Subscription plan (default 'starter').
            status: Approval status — defaults to 'pending' so the tenant
                    cannot log in until a super admin approves it.
        """
        tenant = Tenants(name=name, plan=plan, status=status)
        self.db.add(tenant)
        self.db.flush()  # Flush to get the ID without committing
        return tenant

    def find_all(self):
        """Return all tenants in the system (all statuses)."""
        return self.db.query(Tenants).all()

    def find_all_by_status(self, status: str):
        """Return all tenants with the given status.

        Args:
            status: One of 'pending', 'active', or 'rejected'.
        """
        return self.db.query(Tenants).filter(Tenants.status == status).all()

    def update_status(self, tenant_id: str, status: str):
        """Update a tenant's approval status.

        Args:
            tenant_id: UUID of the tenant.
            status:    New status — 'pending', 'active', or 'rejected'.

        Returns:
            The updated Tenants ORM object, or None if not found.
        """
        tenant = self.find_by_id(tenant_id)
        if not tenant:
            return None
        tenant.status = status
        self.db.flush()
        return tenant

    def delete(self, tenant_id: str) -> bool:
        """Delete a tenant by ID. Returns True if deleted, False if not found."""
        tenant = self.find_by_id(tenant_id)
        if not tenant:
            return False
        self.db.delete(tenant)
        self.db.flush()
        return True

    def update(self, tenant_id: str, name: str = None, plan: str = None):
        """Update tenant name and/or plan. Returns the updated tenant or None if not found."""
        tenant = self.find_by_id(tenant_id)
        if not tenant:
            return None
        if name is not None:
            tenant.name = name
        if plan is not None:
            tenant.plan = plan
        self.db.flush()
        return tenant

    def count_all(self) -> int:
        """Return the total number of tenants in the system."""
        return self.db.query(Tenants).count()

    def commit(self):
        """Commit database changes."""
        self.db.commit()

    def rollback(self):
        """Rollback database changes."""
        self.db.rollback()
