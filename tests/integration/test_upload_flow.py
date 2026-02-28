"""Integration tests for the upload flow combining auth + S3."""

import pytest
import boto3
from moto import mock_aws
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.security import get_current_user, CognitoUser
from app.services.s3 import get_s3_service, S3Service


def make_test_user(sub: str, username: str = "testuser"):
    """Create a test CognitoUser with a specific sub."""
    return CognitoUser(
        sub=sub,
        username=username,
        email=f"{username}@example.com",
        email_verified=True,
        groups=["users"],
        token_use="id",
        iss=settings.COGNITO_ISSUER,
        aud=settings.COGNITO_APP_CLIENT_ID,
        exp=9999999999,
        iat=1000000000,
    )


AUTH_HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture
def s3_env():
    """Set up mocked S3 environment."""
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


def set_current_user(user: CognitoUser):
    """Set the current user for both middleware and dependency."""
    app.dependency_overrides[get_current_user] = lambda: user
    return patch(
        "app.middleware.auth_middleware.verify_cognito_token",
        return_value=user,
    )


class TestFullUploadFlow:
    """Full upload lifecycle: presign → list → metadata → delete."""

    def test_full_upload_flow(self, client, s3_env):
        """Should complete the full upload lifecycle."""
        s3_client, service = s3_env
        user = make_test_user(sub="flow-user-123")

        with set_current_user(user):
            try:
                # Step 1: Generate presigned upload URL
                presign_response = client.post(
                    "/api/v1/upload/presign",
                    json={
                        "filename": "test_video.mp4",
                        "content_type": "video/mp4",
                        "file_size": 2048,
                    },
                    headers=AUTH_HEADERS,
                )
                assert presign_response.status_code == 200
                presign_data = presign_response.json()
                object_key = presign_data["object_key"]
                assert object_key.startswith(f"uploads/{user.sub}/")

                # Step 2: Simulate direct S3 upload
                s3_client.put_object(
                    Bucket="test-bucket",
                    Key=object_key,
                    Body=b"x" * 2048,
                    ContentType="video/mp4",
                )

                # Step 3: List files — should show the uploaded file
                list_response = client.get(
                    "/api/v1/upload/files",
                    headers=AUTH_HEADERS,
                )
                assert list_response.status_code == 200
                list_data = list_response.json()
                assert list_data["count"] == 1
                assert list_data["files"][0]["object_key"] == object_key

                # Step 4: Get file metadata + download URL
                meta_response = client.get(
                    f"/api/v1/upload/files/{object_key}",
                    headers=AUTH_HEADERS,
                )
                assert meta_response.status_code == 200
                meta_data = meta_response.json()
                assert meta_data["filename"] == "test_video.mp4"
                assert meta_data["size"] == 2048
                assert meta_data["download_url"] is not None

                # Step 5: Delete the file
                delete_response = client.delete(
                    f"/api/v1/upload/files/{object_key}",
                    headers=AUTH_HEADERS,
                )
                assert delete_response.status_code == 200

                # Step 6: Verify file is gone
                list_after_delete = client.get(
                    "/api/v1/upload/files",
                    headers=AUTH_HEADERS,
                )
                assert list_after_delete.json()["count"] == 0

            finally:
                app.dependency_overrides.pop(get_current_user, None)


class TestUserIsolation:
    """Tests to verify user A cannot see/access/delete user B's files."""

    def test_user_isolation(self, client, s3_env):
        """User A cannot see or delete User B's files."""
        s3_client, service = s3_env

        user_a = make_test_user(sub="user-a-sub", username="user_a")
        user_b = make_test_user(sub="user-b-sub", username="user_b")

        try:
            # User A uploads a file
            with set_current_user(user_a):
                presign_a = client.post(
                    "/api/v1/upload/presign",
                    json={
                        "filename": "user_a_video.mp4",
                        "content_type": "video/mp4",
                        "file_size": 1024,
                    },
                    headers=AUTH_HEADERS,
                )
                assert presign_a.status_code == 200
                key_a = presign_a.json()["object_key"]

                s3_client.put_object(
                    Bucket="test-bucket",
                    Key=key_a,
                    Body=b"a" * 1024,
                    ContentType="video/mp4",
                )

            # User B uploads a file
            with set_current_user(user_b):
                presign_b = client.post(
                    "/api/v1/upload/presign",
                    json={
                        "filename": "user_b_video.mp4",
                        "content_type": "video/mp4",
                        "file_size": 512,
                    },
                    headers=AUTH_HEADERS,
                )
                assert presign_b.status_code == 200
                key_b = presign_b.json()["object_key"]

                s3_client.put_object(
                    Bucket="test-bucket",
                    Key=key_b,
                    Body=b"b" * 512,
                    ContentType="video/mp4",
                )

                # User B lists files — should only see their own
                list_b = client.get("/api/v1/upload/files", headers=AUTH_HEADERS)
                assert list_b.status_code == 200
                assert list_b.json()["count"] == 1
                assert list_b.json()["files"][0]["object_key"] == key_b

                # User B tries to access User A's file metadata — should get 403
                meta_response = client.get(
                    f"/api/v1/upload/files/{key_a}",
                    headers=AUTH_HEADERS,
                )
                assert meta_response.status_code == 403

                # User B tries to delete User A's file — should get 403
                delete_response = client.delete(
                    f"/api/v1/upload/files/{key_a}",
                    headers=AUTH_HEADERS,
                )
                assert delete_response.status_code == 403

            # Switch back to User A — verify their file is still there
            with set_current_user(user_a):
                list_a = client.get("/api/v1/upload/files", headers=AUTH_HEADERS)
                assert list_a.status_code == 200
                assert list_a.json()["count"] == 1
                assert list_a.json()["files"][0]["object_key"] == key_a

        finally:
            app.dependency_overrides.pop(get_current_user, None)


class TestS3ErrorHandling:
    """Tests for graceful degradation when S3 is unavailable."""

    def test_s3_error_handling(self, client, s3_env):
        """Should return 502 when S3 operations fail."""
        _, service = s3_env
        user = make_test_user(sub="error-user-123")

        with set_current_user(user):
            # Patch the S3 client's list_objects_v2 to raise a ClientError
            from botocore.exceptions import ClientError

            original_list = service._client.list_objects_v2

            def broken_list(*args, **kwargs):
                raise ClientError(
                    {"Error": {"Code": "InternalError", "Message": "S3 unavailable"}},
                    "ListObjectsV2",
                )

            service._client.list_objects_v2 = broken_list

            try:
                list_response = client.get(
                    "/api/v1/upload/files",
                    headers=AUTH_HEADERS,
                )
                assert list_response.status_code == 502

            finally:
                service._client.list_objects_v2 = original_list
                app.dependency_overrides.pop(get_current_user, None)
