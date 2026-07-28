"""Service for handling tenant registration and onboarding."""

import logging
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.hash_service import password_hash
from app.services.token_service import create_access_token
from app.schema.tenant_schema import TenantRegistrationRequest, TenantRegistrationResponse

logger = logging.getLogger(__name__)


class TenantRegistrationService:
    """Service for registering new tenants and their admin users."""
    
    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db
        self.tenant_repo = TenantRepository(db)
        self.user_repo = UserRepository(db)
    
    def register_tenant(self, request: TenantRegistrationRequest) -> TenantRegistrationResponse:
        """
        Register a new tenant with admin user.
        
        Args:
            request: Tenant registration request with org name, admin email, password, etc.
            
        Returns:
            TenantRegistrationResponse with tenant ID, admin email, and access token
            
        Raises:
            HTTPException: If organization name or email already exists
        """
        try:
            # Check if tenant organization name already exists
            existing_tenant = self.tenant_repo.find_by_name(request.organization_name)
            if existing_tenant:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Organization '{request.organization_name}' already exists"
                )
            
            # Check if email already exists
            existing_user = self.user_repo.find_by_email(request.admin_email)
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already registered in system"
                )
            
            # Create new tenant
            tenant = self.tenant_repo.create(
                name=request.organization_name,
                plan=request.plan
            )
            
            # Hash admin password
            hashed_password = password_hash(request.admin_password)
            
            # Create admin user for tenant
            admin_user = self.user_repo.create(
                name=request.admin_name,
                email=request.admin_email,
                hashed_password=hashed_password,
                tenant_id=tenant.id,
                role="admin",
                approval_status="approved"  # Auto-approve first admin
            )
            
            # Commit all changes
            self.tenant_repo.commit()
            
            # Generate access token
            token_data = {
                "sub": admin_user.email,
                "user_id": admin_user.id,
                "tenant_id": tenant.id,
                "role": "admin",
                "approval_status": "approved"
            }
            access_token = create_access_token(data=token_data)
            
            logger.info(f"New tenant registered: {request.organization_name} with admin {request.admin_email}")
            
            # Send welcome email to admin
            try:
                from app.services.email_service import EmailService
                EmailService.send_welcome_email(
                    to_email=admin_user.email,
                    user_name=admin_user.name,
                    org_name=tenant.name
                )
            except Exception as mail_err:
                logger.error(f"Failed to dispatch welcome email to {admin_user.email}: {mail_err}")

            return TenantRegistrationResponse(
                tenant_id=tenant.id,
                admin_id=admin_user.id,
                organization_name=tenant.name,
                admin_email=admin_user.email,
                access_token=access_token,
                plan=tenant.plan,
                message=f"Tenant '{request.organization_name}' created successfully. Admin registered as {request.admin_email}"
            )
        
        except HTTPException:
            self.tenant_repo.rollback()
            raise
        except Exception as e:
            self.tenant_repo.rollback()
            logger.error(f"Error registering tenant: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error registering tenant: {str(e)}"
            )
