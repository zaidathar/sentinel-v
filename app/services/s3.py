"""S3 service for presigned URL generation and file management.

Provides secure, user-scoped file operations with three-layer isolation:
1. S3 key prefix: uploads/{user_sub}/{uuid}_{filename}
2. Service-layer ownership validation on every operation
3. API-layer auth scoping (user_sub from JWT, never from request)
"""

import uuid
from datetime import datetime, timezone

import boto3
import structlog
from botocore.exceptions import ClientError

from app.core.config import settings
from app.core.exceptions import (
    FileAccessDeniedError,
    FileValidationError,
    S3DownloadError,
    S3Error,
    S3UploadError,
)

logger = structlog.get_logger(__name__)

KEY_PREFIX = "uploads"


class S3Service:
    """Service for S3 presigned URL generation and file management."""

    def __init__(self):
        """Initialize S3 client."""
        region = settings.S3_REGION or settings.COGNITO_REGION
        client_kwargs = {
            "region_name": region
        }
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            client_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
            client_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
            
        self._client = boto3.client("s3", **client_kwargs)
        self._bucket = settings.S3_BUCKET_NAME
        logger.info(
            "s3_service_initialized",
            bucket=self._bucket,
            region=region,
        )

    def _validate_ownership(self, user_sub: str, object_key: str) -> None:
        """Validate that the object key belongs to the user.

        Args:
            user_sub: The user's unique identifier from JWT.
            object_key: The S3 object key to validate.

        Raises:
            FileAccessDeniedError: If the object key does not belong to the user.
        """
        expected_prefix = f"{KEY_PREFIX}/{user_sub}/"
        if not object_key.startswith(expected_prefix):
            logger.warning(
                "file_access_denied",
                user_sub=user_sub,
                object_key=object_key,
                expected_prefix=expected_prefix,
            )
            raise FileAccessDeniedError("Access denied")

    def _validate_file(self, content_type: str, file_size: int) -> None:
        """Validate file content type and size.

        Args:
            content_type: MIME type of the file.
            file_size: Size of the file in bytes.

        Raises:
            FileValidationError: If validation fails.
        """
        if content_type not in settings.S3_ALLOWED_CONTENT_TYPES:
            raise FileValidationError(
                f"Content type '{content_type}' is not allowed. "
                f"Allowed types: {settings.S3_ALLOWED_CONTENT_TYPES}"
            )
        if file_size > settings.S3_MAX_FILE_SIZE:
            raise FileValidationError(
                f"File size {file_size} bytes exceeds maximum "
                f"allowed size of {settings.S3_MAX_FILE_SIZE} bytes"
            )

    def _build_object_key(self, user_sub: str, filename: str) -> str:
        """Build a unique, user-scoped S3 object key.

        Args:
            user_sub: The user's unique identifier.
            filename: Original filename.

        Returns:
            S3 object key in format: uploads/{user_sub}/{uuid}_{filename}
        """
        unique_id = uuid.uuid4().hex[:12]
        return f"{KEY_PREFIX}/{user_sub}/{unique_id}_{filename}"

    def _extract_filename(self, object_key: str) -> str:
        """Extract the original filename from an object key.

        Args:
            object_key: S3 object key.

        Returns:
            Original filename without the UUID prefix.
        """
        key_basename = object_key.rsplit("/", 1)[-1]
        if "_" in key_basename and len(key_basename.split("_", 1)[0]) == 12:
            return key_basename.split("_", 1)[1]
        return key_basename

    def generate_upload_url(
        self, user_sub: str, filename: str, content_type: str, file_size: int
    ) -> dict:
        """Generate a presigned POST URL for file upload.

        Args:
            user_sub: The user's unique identifier from JWT.
            filename: Original filename.
            content_type: MIME type of the file.
            file_size: Size of the file in bytes.

        Returns:
            Dict with upload_url, fields, object_key, and expires_in.

        Raises:
            FileValidationError: If file validation fails.
            S3UploadError: If presigned URL generation fails.
        """
        self._validate_file(content_type, file_size)

        object_key = self._build_object_key(user_sub, filename)

        try:
            presigned = self._client.generate_presigned_post(
                Bucket=self._bucket,
                Key=object_key,
                Fields={
                    "Content-Type": content_type,
                },
                Conditions=[
                    {"Content-Type": content_type},
                    ["content-length-range", 1, settings.S3_MAX_FILE_SIZE],
                ],
                ExpiresIn=settings.S3_UPLOAD_EXPIRATION,
            )

            logger.info(
                "presigned_upload_url_generated",
                user_sub=user_sub,
                object_key=object_key,
                content_type=content_type,
                file_size=file_size,
            )

            return {
                "upload_url": presigned["url"],
                "fields": presigned["fields"],
                "object_key": object_key,
                "expires_in": settings.S3_UPLOAD_EXPIRATION,
            }

        except ClientError as e:
            logger.error(
                "presigned_upload_url_failed",
                user_sub=user_sub,
                error=str(e),
            )
            raise S3UploadError(f"Failed to generate upload URL: {e}")

    def generate_download_url(self, user_sub: str, object_key: str) -> str:
        """Generate a presigned GET URL for file download.

        Args:
            user_sub: The user's unique identifier from JWT.
            object_key: S3 object key.

        Returns:
            Presigned download URL string.

        Raises:
            FileAccessDeniedError: If user doesn't own the file.
            S3DownloadError: If presigned URL generation fails.
        """
        self._validate_ownership(user_sub, object_key)

        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": object_key,
                },
                ExpiresIn=settings.S3_DOWNLOAD_EXPIRATION,
            )

            logger.info(
                "presigned_download_url_generated",
                user_sub=user_sub,
                object_key=object_key,
            )

            return url

        except ClientError as e:
            logger.error(
                "presigned_download_url_failed",
                user_sub=user_sub,
                object_key=object_key,
                error=str(e),
            )
            raise S3DownloadError(f"Failed to generate download URL: {e}")

    def list_user_files(self, user_sub: str) -> list[dict]:
        """List all files belonging to a specific user.

        Args:
            user_sub: The user's unique identifier from JWT.

        Returns:
            List of file metadata dicts.

        Raises:
            S3Error: If listing fails.
        """
        prefix = f"{KEY_PREFIX}/{user_sub}/"

        try:
            response = self._client.list_objects_v2(
                Bucket=self._bucket,
                Prefix=prefix,
            )

            files = []
            for obj in response.get("Contents", []):
                files.append({
                    "object_key": obj["Key"],
                    "filename": self._extract_filename(obj["Key"]),
                    "size": obj["Size"],
                    "uploaded_at": obj["LastModified"],
                })

            logger.info(
                "user_files_listed",
                user_sub=user_sub,
                file_count=len(files),
            )

            return files

        except ClientError as e:
            logger.error(
                "list_user_files_failed",
                user_sub=user_sub,
                error=str(e),
            )
            raise S3Error(f"Failed to list files: {e}")

    def get_file_metadata(self, user_sub: str, object_key: str) -> dict:
        """Get metadata for a specific file.

        Args:
            user_sub: The user's unique identifier from JWT.
            object_key: S3 object key.

        Returns:
            Dict with file metadata.

        Raises:
            FileAccessDeniedError: If user doesn't own the file.
            S3Error: If metadata retrieval fails.
        """
        self._validate_ownership(user_sub, object_key)

        try:
            response = self._client.head_object(
                Bucket=self._bucket,
                Key=object_key,
            )

            metadata = {
                "object_key": object_key,
                "filename": self._extract_filename(object_key),
                "content_type": response.get(
                    "ContentType", "application/octet-stream"
                ),
                "size": response["ContentLength"],
                "uploaded_at": response["LastModified"],
            }

            logger.info(
                "file_metadata_retrieved",
                user_sub=user_sub,
                object_key=object_key,
            )

            return metadata

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey"):
                logger.warning(
                    "file_not_found",
                    user_sub=user_sub,
                    object_key=object_key,
                )
                raise S3Error(f"File not found: {object_key}")
            logger.error(
                "get_file_metadata_failed",
                user_sub=user_sub,
                object_key=object_key,
                error=str(e),
            )
            raise S3Error(f"Failed to get file metadata: {e}")

    def delete_file(self, user_sub: str, object_key: str) -> None:
        """Delete a user's file from S3.

        Args:
            user_sub: The user's unique identifier from JWT.
            object_key: S3 object key.

        Raises:
            FileAccessDeniedError: If user doesn't own the file.
            S3Error: If deletion fails.
        """
        self._validate_ownership(user_sub, object_key)

        try:
            self._client.delete_object(
                Bucket=self._bucket,
                Key=object_key,
            )

            logger.info(
                "file_deleted",
                user_sub=user_sub,
                object_key=object_key,
            )

        except ClientError as e:
            logger.error(
                "delete_file_failed",
                user_sub=user_sub,
                object_key=object_key,
                error=str(e),
            )
            raise S3Error(f"Failed to delete file: {e}")


def get_s3_service() -> S3Service:
    """Factory function / FastAPI dependency for S3Service.

    Returns:
        S3Service instance.
    """
    return S3Service()
