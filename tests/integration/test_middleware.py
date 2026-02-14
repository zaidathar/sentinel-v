"""Integration tests for authentication middleware."""

import pytest
from fastapi.testclient import TestClient
from app.core.config import settings


class TestAuthenticationMiddleware:
    """Test suite for middleware-specific functionality."""
    
    def test_public_path_bypass(self, client):
        """Test that middleware bypasses authentication for public paths."""
        public_paths = [
            "/",
            "/health",
            f"{settings.API_V1_STR}/health",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]
        
        for path in public_paths:
            response = client.get(path, follow_redirects=False)
            # Should not return 401
            assert response.status_code != 401
    
    def test_token_extraction_from_header(self, client, valid_token, mock_jwks_client):
        """Test proper extraction of token from Authorization header."""
        response = client.get(
            f"{settings.API_V1_STR}/profile",
            headers={"Authorization": f"Bearer {valid_token}"}
        )
        assert response.status_code == 200
    
    def test_401_response_format_from_middleware(self, client):
        """Test that middleware returns properly formatted 401 responses."""
        response = client.get(f"{settings.API_V1_STR}/profile")
        
        assert response.status_code == 401
        assert "detail" in response.json()
        assert "WWW-Authenticate" in response.headers
    
    def test_middleware_handles_various_invalid_formats(self, client):
        """Test middleware handling of various invalid auth formats."""
        invalid_headers = [
            "invalid",
            "bearer",  # lowercase
            "Bearer",  # Missing token
            "Basic user:pass",  # Wrong scheme
            "",
        ]
        
        for auth_header in invalid_headers:
            response = client.get(
                f"{settings.API_V1_STR}/profile",
                headers={"Authorization": auth_header} if auth_header else {}
            )
            assert response.status_code == 401
    
    def test_middleware_performance_overhead(self, client, valid_token, mock_jwks_client):
        """Test that middleware doesn't add significant overhead."""
        import time
        
        # Make multiple requests and measure time
        start = time.time()
        for _ in range(10):
            response = client.get(
                f"{settings.API_V1_STR}/profile",
                headers={"Authorization": f"Bearer {valid_token}"}
            )
            assert response.status_code == 200
        
        duration = time.time() - start
        
        # Should complete 10 requests in under 2 seconds (very generous)
        assert duration < 2.0
