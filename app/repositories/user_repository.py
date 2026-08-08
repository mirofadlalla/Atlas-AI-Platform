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

    def commit(self):
        """Commit database changes."""
        self.db.commit()

    def rollback(self):
        """Rollback database changes."""
        self.db.rollback()
