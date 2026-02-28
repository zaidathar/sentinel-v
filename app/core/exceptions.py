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


class S3Error(Exception):
    """Base exception for S3-related errors."""
    pass


class S3UploadError(S3Error):
    """Raised when S3 upload operations fail."""
    pass


class S3DownloadError(S3Error):
    """Raised when S3 download operations fail."""
    pass


class FileValidationError(S3Error):
    """Raised when file validation fails (size, type, etc.)."""
    pass


class FileAccessDeniedError(S3Error):
    """Raised when a user tries to access another user's file."""
    pass
