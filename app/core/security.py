"""Production-grade security module with AWS Cognito JWT verification."""

from typing import Optional, List
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from jose.backends import RSAKey
from pydantic import BaseModel, Field
import structlog

from app.core.config import settings
from app.core.jwks import jwks_client
from app.core.exceptions import (
    TokenExpiredError,
    TokenInvalidError,
    AuthenticationError
)

logger = structlog.get_logger(__name__)

security = HTTPBearer()


class CognitoUser(BaseModel):
    """Cognito user model with validated claims."""
    
    sub: str = Field(..., description="User's unique ID (subject)")
    username: str = Field(..., description="Username (cognito:username claim)")
    email: Optional[str] = Field(None, description="User's email address")
    email_verified: Optional[bool] = Field(None, description="Email verification status")
    groups: List[str] = Field(default_factory=list, description="Cognito user groups")
    
    token_use: str = Field(..., description="Token use type (id or access)")
    iss: str = Field(..., description="Token issuer")
    aud: str = Field(..., description="Token audience")
    exp: int = Field(..., description="Expiration timestamp")
    iat: int = Field(..., description="Issued at timestamp")


def verify_cognito_token(token: str) -> CognitoUser:
    """
    Verify and decode a Cognito JWT token with full signature validation.
    
    Args:
        token: The JWT token string
        
    Returns:
        CognitoUser object with validated claims
        
    Raises:
        TokenExpiredError: If token has expired
        TokenInvalidError: If token signature or claims are invalid
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        
        if not kid:
            logger.warning("token_missing_kid")
            raise TokenInvalidError("Token missing 'kid' in header")
        
        jwk = jwks_client.get_signing_key(kid)
        public_key = RSAKey(jwk, algorithm="RS256")
        
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=settings.COGNITO_APP_CLIENT_ID,
            issuer=settings.COGNITO_ISSUER,
            options={
                "verify_signature": True,
                "verify_aud": True,
                "verify_iss": True,
                "verify_exp": True,
            }
        )
        
        sub = payload.get("sub")
        username = payload.get("cognito:username") or payload.get("username")
        
        if not sub:
            logger.warning("token_missing_sub", payload=payload)
            raise TokenInvalidError("Token missing 'sub' claim")
        
        if not username:
            logger.warning("token_missing_username", payload=payload)
            raise TokenInvalidError("Token missing 'cognito:username' or 'username' claim")
        
        email = payload.get("email")
        email_verified = payload.get("email_verified")
        groups = payload.get("cognito:groups", [])
        
        user = CognitoUser(
            sub=sub,
            username=username,
            email=email,
            email_verified=email_verified,
            groups=groups if isinstance(groups, list) else [],
            token_use=payload.get("token_use", ""),
            iss=payload.get("iss", ""),
            aud=payload.get("aud", ""),
            exp=payload.get("exp", 0),
            iat=payload.get("iat", 0),
        )
        
        logger.info(
            "token_verified",
            username=user.username,
            sub=user.sub,
            groups=user.groups
        )
        
        return user
        
    except jwt.ExpiredSignatureError:
        logger.warning("token_expired")
        raise TokenExpiredError("Token has expired")
    
    except JWTError as e:
        logger.warning("token_invalid", error=str(e))
        raise TokenInvalidError(f"Invalid token: {e}")
    
    except AuthenticationError:
        raise
    
    except Exception as e:
        logger.error("token_verification_unexpected_error", error=str(e))
        raise TokenInvalidError(f"Token verification failed: {e}")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> CognitoUser:
    """
    FastAPI dependency to get the current authenticated user.
    
    This validates the JWT token and returns the user information.
    
    Args:
        credentials: HTTP Bearer token from Authorization header
        
    Returns:
        CognitoUser object with validated claims
        
    Raises:
        HTTPException: 401 if authentication fails
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        user = verify_cognito_token(token)
        return user
        
    except TokenExpiredError as e:
        logger.warning("auth_failed_expired", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    except TokenInvalidError as e:
        logger.warning("auth_failed_invalid", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    except Exception as e:
        logger.error("auth_failed_unexpected", error=str(e))
        raise credentials_exception
