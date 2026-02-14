"""Integration tests for end-to-end authentication flow."""

import pytest
from fastapi.testclient import TestClient
from app.core.config import settings


class TestAuthenticationFlow:
    """Integration tests for complete authentication flow."""
    
    def test_public_endpoint_accessible_without_auth(self, client):
        """Test that public endpoints are accessible without authentication."""
        # Root endpoint
        response = client.get("/")
        assert response.status_code == 200
        
        # Health endpoint
        response = client.get(f"{settings.API_V1_STR}/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    
    def test_protected_endpoint_rejects_missing_token(self, client):
        """Test that protected endpoints reject requests without authorization."""
        response = client.get(f"{settings.API_V1_STR}/profile")
        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"
    
    def test_protected_endpoint_rejects_invalid_format(self, client):
        """Test rejection of invalid authentication header format."""
        # Missing 'Bearer' prefix
        response = client.get(
            f"{settings.API_V1_STR}/profile",
            headers={"Authorization": "invalid-format-token"}
        )
        assert response.status_code == 401
        assert "Invalid authentication format" in response.json()["detail"]
    
    def test_protected_endpoint_rejects_invalid_token(self, client):
        """Test rejection of invalid JWT tokens."""
        response = client.get(
            f"{settings.API_V1_STR}/profile",
            headers={"Authorization": "Bearer invalid.jwt.token"}
        )
        assert response.status_code == 401
        assert "Invalid token" in response.json()["detail"] or "Not enough segments" in response.json()["detail"]
    
    def test_protected_endpoint_rejects_expired_token(self, client, expired_token, mock_jwks_client):
        """Test rejection of expired tokens."""
        response = client.get(
            f"{settings.API_V1_STR}/profile",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()
    
    def test_protected_endpoint_accepts_valid_token(self, client, valid_token, mock_jwks_client):
        """Test successful access with valid token."""
        response = client.get(
            f"{settings.API_V1_STR}/profile",
            headers={"Authorization": f"Bearer {valid_token}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["username"] == "testuser"
        assert data["sub"] == "test-user-sub-123"
        assert data["email"] == "test@example.com"
        assert "users" in data["groups"]
    
    def test_middleware_filters_before_routing(self, client, invalid_signature_token, mock_jwks_client):
        """Test that middleware filters requests before they reach handlers."""
        # Invalid signature should be caught by middleware
        response = client.get(
            f"{settings.API_V1_STR}/profile",
            headers={"Authorization": f"Bearer {invalid_signature_token}"}
        )
        assert response.status_code == 401
    
    def test_error_response_format(self, client):
        """Test that error responses are properly formatted."""
        response = client.get(f"{settings.API_V1_STR}/profile")
        
        assert response.status_code == 401
        assert "detail" in response.json()
        assert "WWW-Authenticate" in response.headers
        assert response.headers["WWW-Authenticate"] == "Bearer"
