"""User profile endpoint demonstrating protected routes."""

from fastapi import APIRouter, Depends
from app.core import get_current_user, CognitoUser

router = APIRouter()


@router.get("/profile")
async def get_profile(current_user: CognitoUser = Depends(get_current_user)):
    """
    Get current user's profile information.
    
    This endpoint is protected and requires a valid JWT token.
    The middleware validates the token, and this dependency
    provides access to the validated user object.
    """
    return {
        "username": current_user.username,
        "sub": current_user.sub,
        "email": current_user.email,
        "email_verified": current_user.email_verified,
        "groups": current_user.groups,
        "token_use": current_user.token_use,
    }
