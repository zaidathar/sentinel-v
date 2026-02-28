"""Unit tests for S3 service layer."""

import pytest
import boto3
from moto import mock_aws
from unittest.mock import patch

from app.core.config import settings
from app.services.s3 import S3Service
from app.core.exceptions import (
    FileAccessDeniedError,
    FileValidationError,
    S3UploadError,
    S3Error,
)


@pytest.fixture
def s3_bucket():
    """Create a mock S3 bucket for testing."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        yield s3


@pytest.fixture
def s3_service(s3_bucket):
    """Create an S3Service instance with mocked S3."""
    with patch.object(settings, "S3_BUCKET_NAME", "test-bucket"), \
         patch.object(settings, "S3_REGION", "us-east-1"):
        service = S3Service()
        yield service


class TestGenerateUploadUrl:
    """Tests for presigned upload URL generation."""

    def test_generate_upload_url_success(self, s3_service):
        """Should generate a valid presigned upload URL."""
        result = s3_service.generate_upload_url(
            user_sub="user-123",
            filename="video.mp4",
            content_type="video/mp4",
            file_size=1024,
        )

        assert "upload_url" in result
        assert "fields" in result
        assert "object_key" in result
        assert "expires_in" in result
        assert result["object_key"].startswith("uploads/user-123/")
        assert result["object_key"].endswith("_video.mp4")
        assert result["expires_in"] == settings.S3_UPLOAD_EXPIRATION

    def test_generate_upload_url_invalid_content_type(self, s3_service):
        """Should reject disallowed MIME types."""
        with pytest.raises(FileValidationError, match="not allowed"):
            s3_service.generate_upload_url(
                user_sub="user-123",
                filename="doc.pdf",
                content_type="application/pdf",
                file_size=1024,
            )

    def test_generate_upload_url_exceeds_max_size(self, s3_service):
        """Should reject files exceeding max size."""
        with pytest.raises(FileValidationError, match="exceeds maximum"):
            s3_service.generate_upload_url(
                user_sub="user-123",
                filename="large.mp4",
                content_type="video/mp4",
                file_size=settings.S3_MAX_FILE_SIZE + 1,
            )


class TestGenerateDownloadUrl:
    """Tests for presigned download URL generation."""

    def test_generate_download_url_success(self, s3_service):
        """Should generate a valid presigned download URL."""
        url = s3_service.generate_download_url(
            user_sub="user-123",
            object_key="uploads/user-123/abc123_video.mp4",
        )
        assert isinstance(url, str)
        assert "test-bucket" in url

    def test_generate_download_url_wrong_user(self, s3_service):
        """Should deny access when user doesn't own the file."""
        with pytest.raises(FileAccessDeniedError, match="Access denied"):
            s3_service.generate_download_url(
                user_sub="user-456",
                object_key="uploads/user-123/abc123_video.mp4",
            )


class TestListUserFiles:
    """Tests for listing user's files."""

    def test_list_user_files(self, s3_service, s3_bucket):
        """Should list only files belonging to the specific user."""
        # Upload files for two different users
        s3_bucket.put_object(
            Bucket="test-bucket",
            Key="uploads/user-123/aaa_video1.mp4",
            Body=b"content1",
            ContentType="video/mp4",
        )
        s3_bucket.put_object(
            Bucket="test-bucket",
            Key="uploads/user-123/bbb_video2.mp4",
            Body=b"content2",
            ContentType="video/mp4",
        )
        s3_bucket.put_object(
            Bucket="test-bucket",
            Key="uploads/user-456/ccc_other.mp4",
            Body=b"content3",
            ContentType="video/mp4",
        )

        files = s3_service.list_user_files(user_sub="user-123")

        assert len(files) == 2
        keys = [f["object_key"] for f in files]
        assert "uploads/user-123/aaa_video1.mp4" in keys
        assert "uploads/user-123/bbb_video2.mp4" in keys
        # User 456's files should NOT appear
        assert "uploads/user-456/ccc_other.mp4" not in keys

    def test_list_user_files_empty(self, s3_service):
        """Should return empty list for user with no files."""
        files = s3_service.list_user_files(user_sub="user-nofiles")
        assert files == []


class TestDeleteFile:
    """Tests for file deletion."""

    def test_delete_file_success(self, s3_service, s3_bucket):
        """Should delete the file and confirm removal."""
        s3_bucket.put_object(
            Bucket="test-bucket",
            Key="uploads/user-123/abc_video.mp4",
            Body=b"content",
        )

        s3_service.delete_file(
            user_sub="user-123",
            object_key="uploads/user-123/abc_video.mp4",
        )

        # Verify file is deleted
        response = s3_bucket.list_objects_v2(
            Bucket="test-bucket",
            Prefix="uploads/user-123/abc_video.mp4",
        )
        assert response.get("KeyCount", 0) == 0

    def test_delete_file_wrong_user(self, s3_service, s3_bucket):
        """Should reject deletion of another user's file."""
        s3_bucket.put_object(
            Bucket="test-bucket",
            Key="uploads/user-123/abc_video.mp4",
            Body=b"content",
        )

        with pytest.raises(FileAccessDeniedError, match="Access denied"):
            s3_service.delete_file(
                user_sub="user-456",
                object_key="uploads/user-123/abc_video.mp4",
            )


class TestGetFileMetadata:
    """Tests for file metadata retrieval."""

    def test_get_file_metadata_success(self, s3_service, s3_bucket):
        """Should return file metadata."""
        s3_bucket.put_object(
            Bucket="test-bucket",
            Key="uploads/user-123/abc123456789_video.mp4",
            Body=b"x" * 1024,
            ContentType="video/mp4",
        )

        metadata = s3_service.get_file_metadata(
            user_sub="user-123",
            object_key="uploads/user-123/abc123456789_video.mp4",
        )

        assert metadata["object_key"] == "uploads/user-123/abc123456789_video.mp4"
        assert metadata["filename"] == "video.mp4"
        assert metadata["content_type"] == "video/mp4"
        assert metadata["size"] == 1024

    def test_get_file_metadata_wrong_user(self, s3_service, s3_bucket):
        """Should deny access when user doesn't own the file."""
        s3_bucket.put_object(
            Bucket="test-bucket",
            Key="uploads/user-123/abc_video.mp4",
            Body=b"content",
        )

        with pytest.raises(FileAccessDeniedError, match="Access denied"):
            s3_service.get_file_metadata(
                user_sub="user-456",
                object_key="uploads/user-123/abc_video.mp4",
            )


class TestObjectKeyFormat:
    """Tests for object key generation and parsing."""

    def test_object_key_format(self, s3_service):
        """Should generate keys in format: uploads/{sub}/{uuid}_{filename}."""
        result = s3_service.generate_upload_url(
            user_sub="user-abc-123",
            filename="my_video.mp4",
            content_type="video/mp4",
            file_size=1024,
        )

        key = result["object_key"]
        parts = key.split("/")
        assert parts[0] == "uploads"
        assert parts[1] == "user-abc-123"
        assert parts[2].endswith("_my_video.mp4")
        # UUID part should be 12 hex chars
        uuid_part = parts[2].split("_", 1)[0]
        assert len(uuid_part) == 12

    def test_extract_filename(self, s3_service):
        """Should extract original filename from object key."""
        filename = s3_service._extract_filename(
            "uploads/user-123/abc123456789_original_file.mp4"
        )
        assert filename == "original_file.mp4"
