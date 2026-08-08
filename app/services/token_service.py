from jose import jwt
from datetime import datetime, timedelta

from app.core.config import settings

# Fail hard at startup if no secret key is configured — never fall back to a known string
if not settings.api_secret_key:
    raise RuntimeError(
        "API_SECRET_KEY is not set in your environment or .env file. "
        "Generate a strong random secret and set it before starting the server."
    )

SECRET_KEY = settings.api_secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token with the given data and expiration time."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str):
    """Decode and validate a JWT access token. Raises JWTError on failure."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
