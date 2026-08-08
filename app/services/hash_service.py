from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],  # يدعم الاتنين
    default="argon2",
    deprecated="auto",
)


def password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
