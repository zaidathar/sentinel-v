"""Custom exceptions for authentication and security."""

class AuthenticationError(Exception):
    """Base exception for all authentication-related errors."""
    pass


class TokenExpiredError(AuthenticationError):
    """Raised when a JWT token has expired."""
    pass


class TokenInvalidError(AuthenticationError):
    """Raised when a JWT token is invalid (signature, format, claims, etc.)."""
    pass


class JWKSFetchError(AuthenticationError):
    """Raised when fetching JWKS keys from Cognito fails."""
    pass
