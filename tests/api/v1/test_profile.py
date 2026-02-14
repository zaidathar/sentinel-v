"""Tests for profile endpoint."""

import pytest
from app.core.config import settings


def test_profile_requires_authentication(client):
    """Test that profile endpoint requires authentication."""
    response = client.get(f"{settings.API_V1_STR}/profile")
    assert response.status_code == 401


def test_profile_rejects_invalid_token(client):
    """Test profile endpoint rejects invalid tokens."""
    response = client.get(
        f"{settings.API_V1_STR}/profile",
        headers={"Authorization": "Bearer invalid-token"}
    )
    assert response.status_code == 401


def test_profile_returns_user_data_with_valid_token(client, valid_token, mock_jwks_client):
    """Test profile endpoint returns user data with valid token."""
    response = client.get(
        f"{settings.API_V1_STR}/profile",
        headers={"Authorization": f"Bearer {valid_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "username" in data
    assert "sub" in data
    assert "email" in data
    assert "groups" in data
    assert data["username"] == "testuser"
    assert data["sub"] == "test-user-sub-123"


def test_profile_handles_missing_optional_claims(client, rsa_key_pair, mock_jwks_client):
    """Test profile endpoint handles tokens with missing optional claims."""
    from jose import jwt
    import time
    
    now = int(time.time())
    payload = {
        "sub": "test-user",
        "cognito:username": "minimaluser",
        "iss": settings.COGNITO_ISSUER,
        "aud": settings.COGNITO_APP_CLIENT_ID,
        "exp": now + 3600,
        "iat": now,
        "token_use": "id",
    }
    
    headers = {"kid": "test-key-id-123"}
    token = jwt.encode(payload, rsa_key_pair["private_key"], algorithm="RS256", headers=headers)
    
    response = client.get(
        f"{settings.API_V1_STR}/profile",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "minimaluser"
    assert data["email"] is None
    assert data["groups"] == []
