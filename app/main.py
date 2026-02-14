"""Main FastAPI application with production-grade security."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from mangum import Mangum
import structlog

from app.core import logging as _  # noqa: F401
from app.core.config import settings
from app.core.exceptions import AuthenticationError, JWKSFetchError
from app.api.v1.api import api_router
from app.middleware import AuthenticationMiddleware

logger = structlog.get_logger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(AuthenticationMiddleware)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": f"{settings.PROJECT_NAME} API is running",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request: Request, exc: AuthenticationError):
    """Handle authentication errors."""
    logger.warning(
        "authentication_error",
        path=request.url.path,
        error=str(exc),
        error_type=type(exc).__name__
    )
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": str(exc)},
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.exception_handler(JWKSFetchError)
async def jwks_fetch_error_handler(request: Request, exc: JWKSFetchError):
    """Handle JWKS fetching errors."""
    logger.error(
        "jwks_fetch_error",
        path=request.url.path,
        error=str(exc)
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Authentication service temporarily unavailable"},
    )


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    logger.info(
        "application_startup",
        project=settings.PROJECT_NAME,
        cognito_region=settings.COGNITO_REGION,
        testing_mode=settings.TESTING_MODE,
    )
    
    try:
        jwks_url = settings.COGNITO_JWKS_URL
        logger.info("cognito_configuration_validated", jwks_url=jwks_url)
    except Exception as e:
        logger.error("cognito_configuration_invalid", error=str(e))
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    logger.info("application_shutdown", project=settings.PROJECT_NAME)


handler = Mangum(app)
