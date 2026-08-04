from sqlalchemy.orm import Session
from app.schema.auth_admin import UserCreate
from fastapi import HTTPException, status

from app.repositories.user_repository import UserRepository
from app.repositories.tenant_repository import TenantRepository

from app.services.hash_service import password_hash, verify_password
from app.services.token_service import create_access_token

class AuthService:
    '''
    Docstring for AuthService
    # This service handles authentication and registration logic for admin users in a multi-tenant application.
    It interacts with the UserRepository and TenantRepository to manage user and tenant data,
    and uses hashing and token services to securely handle passwords and authentication tokens.
    '''
    def __init__(self, db: Session):
        self.user_repo = UserRepository(db)
        self.tenant_repo = TenantRepository(db)

    # Register a new admin user and create a tenant 
    def register_user(self, user_data: UserCreate):
        # Check if user exists
        existing_user = self.user_repo.find_by_email(user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Email already registered"
            )
        
        # Check tenant
        tenant_obj = self.tenant_repo.find_by_name(user_data.tenant_name)

        if tenant_obj:
            raise HTTPException(
                status_code=404,
                detail="Tenant already exists"
            )
        
        tenant_obj =  self.tenant_repo.create(user_data.tenant_name)

        # Create admin
        hashed_password = password_hash(user_data.password)
        new_user = self.user_repo.create(user_data.name,
                                          user_data.email,
                                            hashed_password,
                                              tenant_obj.id,
                                                role="admin"
                                        )
        
        # Generate token
        access_token = create_access_token({
            "sub": new_user.email, 
            "user_id": new_user.id,
            "role": new_user.role,
            "approval_status": new_user.approval_status,
            "tenant_id": tenant_obj.id
        })
        
        return {
            "access_token": access_token, 
            "token_type": "bearer"
        }

    # Login user and return access token
    def login_user(self, email: str, password: str):
        user = self.user_repo.find_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Block pending/rejected users before issuing any token
        if user.approval_status == "pending":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is awaiting admin approval.",
            )
        if user.approval_status == "rejected":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account registration was not approved.",
            )

        access_token = create_access_token({
            "sub": user.email,
            "user_id": user.id,
            "role": user.role,
            "approval_status": user.approval_status,
            "tenant_id": user.tenant_id
        })

        return {
            "access_token": access_token,
            "token_type": "bearer"
        }