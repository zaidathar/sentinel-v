"""Pytest configuration and comprehensive fixtures for testing."""

import pytest
import time
import json
from typing import Dict, Any
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from jose import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from app.main import app
from app.core.config import settings


@pytest.fixture(scope="module")
def client():
    """Test client fixture for making requests to the FastAPI app."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def rsa_key_pair():
    """Generate RSA key pair for test JWT signing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    public_key = private_key.public_key()
    
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    return {
        "private_key": private_key,
        "public_key": public_key,
        "private_pem": private_pem,
        "public_pem": public_pem,
    }


@pytest.fixture(scope="session")
def jwks_response(rsa_key_pair) -> Dict[str, Any]:
    """Mock JWKS response with test public key."""
    from jose.backends.cryptography_backend import CryptographyRSAKey
    
    jwk_key = CryptographyRSAKey(rsa_key_pair["public_key"], "RS256")
    jwk_dict = jwk_key.to_dict()
    
    jwk_dict["kid"] = "test-key-id-123"
    jwk_dict["alg"] = "RS256"
    jwk_dict["use"] = "sig"
    
    return {"keys": [jwk_dict]}

@pytest.fixture
def valid_token(rsa_key_pair):
    """Generate a valid JWT token for testing."""
    now = int(time.time())
    
    payload = {
        "sub": "test-user-sub-123",
        "cognito:username": "testuser",
        "email": "test@example.com",
        "email_verified": True,
        "cognito:groups": ["users", "admins"],
        "token_use": "id",
        "iss": settings.COGNITO_ISSUER,
        "aud": settings.COGNITO_APP_CLIENT_ID,
        "exp": now + 3600,
        "iat": now,
    }
    
    headers = {"kid": "test-key-id-123"}
    
    token = jwt.encode(
        payload,
        rsa_key_pair["private_key"],
        algorithm="RS256",
        headers=headers
    )
    
    return token


@pytest.fixture
def expired_token(rsa_key_pair):
    """Generate an expired JWT token for testing."""
    now = int(time.time())
    
    payload = {
        "sub": "test-user-sub-456",
        "cognito:username": "expireduser",
        "email": "expired@example.com",
        "token_use": "id",
        "iss": settings.COGNITO_ISSUER,
        "aud": settings.COGNITO_APP_CLIENT_ID,
        "exp": now - 3600,
        "iat": now - 7200,
    }
    
    headers = {"kid": "test-key-id-123"}
    
    token = jwt.encode(
        payload,
        rsa_key_pair["private_key"],
        algorithm="RS256",
        headers=headers
    )
    
    return token


@pytest.fixture
def invalid_signature_token(valid_token, rsa_key_pair):
    """Generate a token with tampered signature for testing."""
    wrong_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    now = int(time.time())
    payload = {
        "sub": "test-user-sub-789",
        "cognito:username": "invaliduser",
        "token_use": "id",
        "iss": settings.COGNITO_ISSUER,
        "aud": settings.COGNITO_APP_CLIENT_ID,
        "exp": now + 3600,
        "iat": now,
    }
    
    headers = {"kid": "test-key-id-123"}
    
    token = jwt.encode(
        payload,
        wrong_key,
        algorithm="RS256",
        headers=headers
    )
    
    return token


@pytest.fixture
def token_missing_claims(rsa_key_pair):
    """Generate a token missing required claims."""
    now = int(time.time())
    
    payload = {
        "email": "incomplete@example.com",
        "token_use": "id",
        "iss": settings.COGNITO_ISSUER,
        "aud": settings.COGNITO_APP_CLIENT_ID,
        "exp": now + 3600,
        "iat": now,
    }
    
    headers = {"kid": "test-key-id-123"}
    
    token = jwt.encode(
        payload,
        rsa_key_pair["private_key"],
        algorithm="RS256",
        headers=headers
    )
    
    return token

@pytest.fixture
def mock_jwks_client(jwks_response):
    """Mock JWKS client for testing."""
    with patch("app.core.jwks.requests.get") as mock_get:
        mock_response = Mock()
        mock_response.json.return_value = jwks_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        yield mock_get

@pytest.fixture
def override_settings():
    """
    Fixture to override settings for testing.
    Usage:
        def test_something(override_settings):
            override_settings({"TESTING_MODE": True})
    """
    original_values = {}
    
    def _override(**kwargs):
        for key, value in kwargs.items():
            if hasattr(settings, key):
                original_values[key] = getattr(settings, key)
                setattr(settings, key, value)
    
    yield _override
    for key, value in original_values.items():
        setattr(settings, key, value)
