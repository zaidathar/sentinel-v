"""API tests for upload endpoints."""

import pytest
import boto3
from moto import mock_aws
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.security import get_current_user, CognitoUser
from app.services.s3 import get_s3_service, S3Service


def make_test_user(sub: str = "test-user-sub-123", username: str = "testuser"):
    """Create a test CognitoUser."""
    return CognitoUser(
        sub=sub,
        username=username,
        email="test@example.com",
        email_verified=True,
        groups=["users"],
        token_use="id",
        iss=settings.COGNITO_ISSUER,
        aud=settings.COGNITO_APP_CLIENT_ID,
        exp=9999999999,
        iat=1000000000,
    )


@pytest.fixture
def test_user():
    """Default test user."""
    return make_test_user()


@pytest.fixture
def mock_auth(test_user):
    """
    Override auth dependency and patch middleware to accept test requests.
    The middleware runs before FastAPI dependencies, so we need to patch
    verify_cognito_token at the middleware level too.
    """
    app.dependency_overrides[get_current_user] = lambda: test_user

    with patch(
        "app.middleware.auth_middleware.verify_cognito_token",
        return_value=test_user,
    ):
        yield test_user

    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def mock_s3():
    """Mock S3 service with moto."""
    with mock_aws():
        s3_client = boto3.client("s3", region_name="us-east-1")
        s3_client.create_bucket(Bucket="test-bucket")

        with patch.object(settings, "S3_BUCKET_NAME", "test-bucket"), \
             patch.object(settings, "S3_REGION", "us-east-1"):
            service = S3Service()
            app.dependency_overrides[get_s3_service] = lambda: service
            yield s3_client, service
            app.dependency_overrides.pop(get_s3_service, None)


@pytest.fixture
def client():
    """Test client."""
    return TestClient(app)


def auth_headers():
    """Return auth headers with a dummy token (middleware is mocked)."""
    return {"Authorization": "Bearer test-token"}


class TestPresignUpload:
    """Tests for POST /api/v1/upload/presign."""

    def test_presign_upload_authenticated(self, client, mock_auth, mock_s3):
        """Should return presigned URL for valid request."""
        response = client.post(
            "/api/v1/upload/presign",
            json={
                "filename": "video.mp4",
                "content_type": "video/mp4",
                "file_size": 1024,
            },
            headers=auth_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert "upload_url" in data
        assert "fields" in data
        assert "object_key" in data
        assert data["object_key"].startswith(f"uploads/{mock_auth.sub}/")
        assert data["expires_in"] == settings.S3_UPLOAD_EXPIRATION

    def test_presign_upload_unauthenticated(self, client):
        """Should return 401 without token."""
        app.dependency_overrides.pop(get_current_user, None)

        response = client.post(
            "/api/v1/upload/presign",
            json={
                "filename": "video.mp4",
                "content_type": "video/mp4",
                "file_size": 1024,
            },
        )

        assert response.status_code == 401

    def test_presign_upload_invalid_content_type(self, client, mock_auth, mock_s3):
        """Should return 422 for disallowed MIME type."""
        response = client.post(
            "/api/v1/upload/presign",
            json={
                "filename": "document.pdf",
                "content_type": "application/pdf",
                "file_size": 1024,
            },
            headers=auth_headers(),
        )

        assert response.status_code == 422
        assert "not allowed" in response.json()["detail"]

    def test_presign_upload_exceeds_size(self, client, mock_auth, mock_s3):
        """Should return 422 for oversized file."""
        response = client.post(
            "/api/v1/upload/presign",
            json={
                "filename": "large.mp4",
                "content_type": "video/mp4",
                "file_size": settings.S3_MAX_FILE_SIZE + 1,
            },
            headers=auth_headers(),
        )

        assert response.status_code == 422
        assert "exceeds maximum" in response.json()["detail"]


class TestListFiles:
    """Tests for GET /api/v1/upload/files."""

    def test_list_files_authenticated(self, client, mock_auth, mock_s3):
        """Should return user's file list."""
        s3_client, _ = mock_s3

        # Upload a test file
        s3_client.put_object(
            Bucket="test-bucket",
            Key=f"uploads/{mock_auth.sub}/abc123456789_video.mp4",
            Body=b"content",
            ContentType="video/mp4",
        )

        response = client.get("/api/v1/upload/files", headers=auth_headers())

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert len(data["files"]) == 1
        assert data["files"][0]["filename"] == "video.mp4"

    def test_list_files_unauthenticated(self, client):
        """Should return 401 without token."""
        app.dependency_overrides.pop(get_current_user, None)

        response = client.get("/api/v1/upload/files")
        assert response.status_code == 401

    def test_list_files_empty(self, client, mock_auth, mock_s3):
        """Should return empty list when user has no files."""
        response = client.get("/api/v1/upload/files", headers=auth_headers())

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["files"] == []


class TestGetFileMetadata:
    """Tests for GET /api/v1/upload/files/{object_key}."""

    def test_get_file_metadata(self, client, mock_auth, mock_s3):
        """Should return metadata + download URL."""
        s3_client, _ = mock_s3
        object_key = f"uploads/{mock_auth.sub}/abc123456789_video.mp4"

        s3_client.put_object(
            Bucket="test-bucket",
            Key=object_key,
            Body=b"x" * 2048,
            ContentType="video/mp4",
        )

        response = client.get(
            f"/api/v1/upload/files/{object_key}",
            headers=auth_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "video.mp4"
        assert data["content_type"] == "video/mp4"
        assert data["size"] == 2048
        assert data["download_url"] is not None

    def test_get_file_metadata_not_found(self, client, mock_auth, mock_s3):
        """Should return 404 for missing file."""
        object_key = f"uploads/{mock_auth.sub}/nonexistent_video.mp4"

        response = client.get(
            f"/api/v1/upload/files/{object_key}",
            headers=auth_headers(),
        )

        assert response.status_code in (404, 502)


class TestDeleteFile:
    """Tests for DELETE /api/v1/upload/files/{object_key}."""

    def test_delete_file_success(self, client, mock_auth, mock_s3):
        """Should delete and return 200."""
        s3_client, _ = mock_s3
        object_key = f"uploads/{mock_auth.sub}/abc123456789_video.mp4"

        s3_client.put_object(
            Bucket="test-bucket",
            Key=object_key,
            Body=b"content",
        )

        response = client.delete(
            f"/api/v1/upload/files/{object_key}",
            headers=auth_headers(),
        )

        assert response.status_code == 200
        assert response.json()["detail"] == "File deleted successfully"

    def test_delete_file_access_denied(self, client, mock_auth, mock_s3):
        """Should return 403 when trying to delete another user's file."""
        s3_client, _ = mock_s3
        object_key = "uploads/other-user-sub/abc123456789_video.mp4"

        s3_client.put_object(
            Bucket="test-bucket",
            Key=object_key,
            Body=b"content",
        )

        response = client.delete(
            f"/api/v1/upload/files/{object_key}",
            headers=auth_headers(),
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"
