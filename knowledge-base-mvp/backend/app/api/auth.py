"""
Authentication API routes.
POST /api/v1/auth/token — validate credentials and return JWT.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.security import authenticate_user, create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    organization_id: str
    username: str


@router.post("/token", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Authenticate user credentials and issue a JWT access token.
    Returns the token, token type, organization ID, and username.
    """
    user = authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": user.username, "org": user.organization_id}
    )

    return TokenResponse(
        access_token=access_token,
        organization_id=user.organization_id,
        username=user.username,
    )
