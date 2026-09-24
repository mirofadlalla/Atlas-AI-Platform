from sqlalchemy.orm import Session
from app.models.user import Users


class UserRepository:
    """Repository for User database operations."""

    def __init__(self, db: Session):
        self.db = db

    def find_by_email(self, email: str):
        """Find user by email."""
        return self.db.query(Users).filter(Users.email == email).first()

    def find_by_email_and_tenant(self, email: str, tenant_id: str):
        """Find user by email scoped to a specific tenant."""
        return (
            self.db.query(Users)
            .filter(Users.email == email, Users.tenant_id == tenant_id)
            .first()
        )

    def find_by_id(self, user_id: str):
        """Find user by ID."""
        return self.db.query(Users).filter(Users.id == user_id).first()

    def create(
        self,
        name: str,
        email: str,
        hashed_password: str,
        tenant_id: str,
        role: str = "user",
        approval_status: str = "approved",
    ):
        """Create a new user."""
        user = Users(
            name=name,
            email=email,
            hashed_password=hashed_password,
            tenant_id=tenant_id,
            role=role,
            approval_status=approval_status,
            approved_by=None,
            approved_at=None,
        )
        self.db.add(user)
        self.db.flush()  # Flush to get the ID without committing
        return user

    def find_all_by_tenant(self, tenant_id: str):
        """Return all users belonging to the specified tenant."""
        return self.db.query(Users).filter(Users.tenant_id == tenant_id).all()

    def find_all(self):
        """Return every user in the system (super admin use only)."""
        return self.db.query(Users).all()

    def delete(self, user_id: str) -> bool:
        """Delete a user by ID. Returns True if deleted, False if not found."""
        user = self.find_by_id(user_id)
        if not user:
            return False
        self.db.delete(user)
        self.db.flush()
        return True

    def update_role(self, user_id: str, role: str):
        """Update a user's role. Returns the updated user or None if not found."""
        user = self.find_by_id(user_id)
        if not user:
            return None
        user.role = role
        self.db.flush()
        return user

    def update_approval_status(self, user_id: str, status: str):
        """Update a user's approval status. Returns the updated user or None if not found."""
        user = self.find_by_id(user_id)
        if not user:
            return None
        user.approval_status = status
        self.db.flush()
        return user

    def count_by_tenant(self, tenant_id: str) -> int:
        """Return the number of users in a given tenant."""
        return self.db.query(Users).filter(Users.tenant_id == tenant_id).count()

    def commit(self):
        """Commit database changes."""
        self.db.commit()

    def rollback(self):
        """Rollback database changes."""
        self.db.rollback()
