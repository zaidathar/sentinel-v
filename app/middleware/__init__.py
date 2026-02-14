"""Middleware package."""

from app.middleware.auth_middleware import AuthenticationMiddleware

__all__ = ["AuthenticationMiddleware"]
