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

    def create(self, name: str, plan: str = "starter"):
        """Create a new tenant."""
        tenant = Tenants(name=name, plan=plan)
        self.db.add(tenant)
        self.db.flush()  # Flush to get the ID without committing
        return tenant

    def commit(self):
        """Commit database changes."""
        self.db.commit()

    def rollback(self):
        """Rollback database changes."""
        self.db.rollback()
