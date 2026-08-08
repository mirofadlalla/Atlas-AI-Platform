from sqlalchemy.orm import Session
from app.services.auth_services.auth_admin_service import AuthService
from app.schema.auth_admin import UserCreate, UserLogin


class AuthController:
    @staticmethod
    def register(user_data: UserCreate, db: Session):
        service = AuthService(db)
        return service.register_user(user_data)

    @staticmethod
    def login(user_data: UserLogin, db: Session):
        service = AuthService(db)
        return service.login_user(user_data.email, user_data.password)
