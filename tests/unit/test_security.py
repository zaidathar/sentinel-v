"""Unit tests for JWT token verification."""

import pytest
import time
from freezegun import freeze_time
from app.core.security import verify_cognito_token, CognitoUser
from app.core.exceptions import TokenExpiredError, TokenInvalidError


class TestTokenVerification:
    """Test suite for JWT token verification."""
    
    def test_valid_token_verification(self, valid_token, mock_jwks_client):
        """Test successful verification of a valid token."""
        user = verify_cognito_token(valid_token)
        
        assert isinstance(user, CognitoUser)
        assert user.username == "testuser"
        assert user.sub == "test-user-sub-123"
        assert user.email == "test@example.com"
        assert user.email_verified is True
        assert "users" in user.groups
        assert "admins" in user.groups
        assert user.token_use == "id"
    
    def test_expired_token_raises_error(self, expired_token, mock_jwks_client):
        """Test that expired tokens raise TokenExpiredError."""
        with pytest.raises(TokenExpiredError) as exc_info:
            verify_cognito_token(expired_token)
        
        assert "expired" in str(exc_info.value).lower()
    
    def test_invalid_signature_raises_error(self, invalid_signature_token, mock_jwks_client):
        """Test that tokens with invalid signatures are rejected."""
        with pytest.raises(TokenInvalidError) as exc_info:
            verify_cognito_token(invalid_signature_token)
        
        assert "invalid" in str(exc_info.value).lower()
    
    def test_missing_kid_header(self, rsa_key_pair):
        """Test token missing 'kid' in header."""
        from jose import jwt
        
        payload = {"sub": "test", "username": "test"}
        # Create token without kid in header
        token = jwt.encode(
            payload,
            rsa_key_pair["private_key"],
            algorithm="RS256"
        )
        
        with pytest.raises(TokenInvalidError) as exc_info:
            verify_cognito_token(token)
        
        assert "kid" in str(exc_info.value).lower()
    
    def test_missing_sub_claim(self, token_missing_claims, mock_jwks_client):
        """Test token missing required 'sub' claim."""
        with pytest.raises(TokenInvalidError) as exc_info:
            verify_cognito_token(token_missing_claims)
        
        assert "sub" in str(exc_info.value).lower()
    
    def test_wrong_issuer(self, rsa_key_pair, mock_jwks_client):
        """Test token with wrong issuer."""
        from jose import jwt
        
        now = int(time.time())
        payload = {
            "sub": "test-user",
            "cognito:username": "testuser",
            "iss": "https://wrong-issuer.com",  # Wrong issuer
            "aud": "test-client-id",
            "exp": now + 3600,
            "iat": now,
            "token_use": "id",
        }
        
        headers = {"kid": "test-key-id-123"}
        token = jwt.encode(payload, rsa_key_pair["private_key"], algorithm="RS256", headers=headers)
        
        with pytest.raises(TokenInvalidError):
            verify_cognito_token(token)
    
    def test_wrong_audience(self, rsa_key_pair, mock_jwks_client):
        """Test token with wrong audience."""
        from jose import jwt
        from app.core.config import settings
        
        now = int(time.time())
        payload = {
            "sub": "test-user",
            "cognito:username": "testuser",
            "iss": settings.COGNITO_ISSUER,
            "aud": "wrong-audience",  # Wrong audience
            "exp": now + 3600,
            "iat": now,
            "token_use": "id",
        }
        
        headers = {"kid": "test-key-id-123"}
        token = jwt.encode(payload, rsa_key_pair["private_key"], algorithm="RS256", headers=headers)
        
        with pytest.raises(TokenInvalidError):
            verify_cognito_token(token)
    
    def test_malformed_token(self):
        """Test completely malformed token."""
        with pytest.raises(TokenInvalidError):
            verify_cognito_token("not-a-jwt-token")
    
    def test_claim_extraction_optional_fields(self, rsa_key_pair, mock_jwks_client):
        """Test extraction of optional claims."""
        from jose import jwt
        from app.core.config import settings
        
        now = int(time.time())
        payload = {
            "sub": "test-user-sub",
            "cognito:username": "testuser",
            # Optional fields omitted
            "iss": settings.COGNITO_ISSUER,
            "aud": settings.COGNITO_APP_CLIENT_ID,
            "exp": now + 3600,
            "iat": now,
            "token_use": "access",
        }
        
        headers = {"kid": "test-key-id-123"}
        token = jwt.encode(payload, rsa_key_pair["private_key"], algorithm="RS256", headers=headers)
        
        user = verify_cognito_token(token)
        
        assert user.username == "testuser"
        assert user.email is None
        assert user.email_verified is None
        assert user.groups == []
