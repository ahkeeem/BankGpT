"""
JWT authentication and password hashing utilities.
Provides FastAPI dependency for extracting current user from bearer tokens.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.config import settings

# --- Password Hashing ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- OAuth2 Scheme ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


# --- Models ---
class TokenData(BaseModel):
    username: str
    organization_id: str


class UserRecord(BaseModel):
    username: str
    hashed_password: str
    organization_id: str


# --- Demo Users (MVP) ---
DEMO_USERS: dict[str, UserRecord] = {
    "admin": UserRecord(
        username="admin",
        hashed_password=pwd_context.hash("admin123"),
        organization_id="demo_org",
    ),
    "uba_user": UserRecord(
        username="uba_user",
        hashed_password=pwd_context.hash("uba123"),
        organization_id="uba",
    ),
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against its bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def authenticate_user(username: str, password: str) -> Optional[UserRecord]:
    """Look up user and verify credentials. Returns UserRecord or None."""
    user = DEMO_USERS.get(username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT token with expiration."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> Optional[TokenData]:
    """
    FastAPI dependency to extract user from JWT bearer token.
    Returns None if no token is provided (allows open access for MVP testing).
    Raises 401 if token is present but invalid.
    """
    if token is None:
        return None

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        username: str = payload.get("sub", "")
        organization_id: str = payload.get("org", "")
        if not username:
            raise credentials_exception
        return TokenData(username=username, organization_id=organization_id)
    except JWTError:
        raise credentials_exception
