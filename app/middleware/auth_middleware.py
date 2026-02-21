"""Authentication middleware for early request filtering."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi import status
import structlog

from app.core.security import verify_cognito_token
from app.core.exceptions import TokenExpiredError, TokenInvalidError, AuthenticationError

logger = structlog.get_logger(__name__)

PUBLIC_PATHS = {
    "/",
    "/health",
    "/api/v1/health",
    "/docs",
    "/redoc",
    "/api/v1/openapi.json",
    "/api/v1/auth/login",
    "/api/v1/auth/callback",
    "/api/v1/auth/token",
}


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce authentication on all non-public endpoints.
    
    This middleware intercepts ALL requests and validates JWT tokens
    BEFORE routing to handlers, providing early security filtering.
    """
    
    async def dispatch(self, request: Request, call_next):
        """Process request and validate authentication."""
        
        path = request.url.path
        
        if path in PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/openapi"):
            return await call_next(request)
        
        auth_header = request.headers.get("Authorization")
        
        if not auth_header:
            logger.warning("auth_middleware_no_token", path=path, client=request.client)
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Not authenticated"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logger.warning("auth_middleware_invalid_format", path=path, auth_header=auth_header[:20])
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid authentication format"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token = parts[1]
        
        try:
            user = verify_cognito_token(token)
            request.state.user = user
            
            logger.info(
                "auth_middleware_success",
                path=path,
                username=user.username,
                sub=user.sub
            )
            
            return await call_next(request)
            
        except TokenExpiredError as e:
            logger.warning("auth_middleware_token_expired", path=path, error=str(e))
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Token has expired"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        except TokenInvalidError as e:
            logger.warning("auth_middleware_token_invalid", path=path, error=str(e))
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": f"Invalid token: {e}"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        except AuthenticationError as e:
            logger.warning("auth_middleware_auth_error", path=path, error=str(e))
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication failed"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        except Exception as e:
            logger.error("auth_middleware_unexpected_error", path=path, error=str(e))
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error"},
            )
