"""Unit tests for JWKS client functionality."""

import pytest
import responses
from unittest.mock import patch
from app.core.jwks import JWKSClient, jwks_client
from app.core.config import settings
from app.core.exceptions import JWKSFetchError


class TestJWKSClient:
    """Test suite for JWKS client."""
    
    @responses.activate
    def test_fetch_keys_success(self, jwks_response):
        """Test successful fetching of JWKS keys."""
        responses.add(
            responses.GET,
            settings.COGNITO_JWKS_URL,
            json=jwks_response,
            status=200
        )
        
        client = JWKSClient()
        key = client.get_signing_key("test-key-id-123")
        
        assert key is not None
        assert key["kid"] == "test-key-id-123"
        assert key["alg"] == "RS256"
        assert key["use"] == "sig"
    
    def test_cache_functionality(self, mock_jwks_client, jwks_response):
        """Test that keys are cached and HTTP calls are minimized."""
        client = JWKSClient()
        client._cache.clear()
        
        key1 = client.get_signing_key("test-key-id-123")
        assert mock_jwks_client.call_count == 1
        
        key2 = client.get_signing_key("test-key-id-123")
        assert mock_jwks_client.call_count == 1
        
        assert key1 == key2
    
    @responses.activate
    def test_network_error_handling(self):
        """Test handling of network errors when fetching JWKS."""
        responses.add(
            responses.GET,
            settings.COGNITO_JWKS_URL,
            body="Network error",
            status=500
        )
        
        client = JWKSClient()
        client._cache.clear()
        
        with pytest.raises(JWKSFetchError) as exc_info:
            client.get_signing_key("test-key-id-123")
        
        assert "Failed to fetch JWKS" in str(exc_info.value)
    
    @responses.activate
    def test_malformed_jwks_response(self):
        """Test handling of malformed JWKS response."""
        responses.add(
            responses.GET,
            settings.COGNITO_JWKS_URL,
            json={"invalid": "structure"},
            status=200
        )
        
        client = JWKSClient()
        client._cache.clear()
        
        with pytest.raises(JWKSFetchError) as exc_info:
            client.get_signing_key("test-key-id-123")
        
        assert "Invalid JWKS response" in str(exc_info.value)
    
    @responses.activate
    def test_kid_not_found(self, jwks_response):
        """Test handling when requested key ID is not in JWKS."""
        responses.add(
            responses.GET,
            settings.COGNITO_JWKS_URL,
            json=jwks_response,
            status=200
        )
        
        client = JWKSClient()
        client._cache.clear()
        
        with pytest.raises(JWKSFetchError) as exc_info:
            client.get_signing_key("non-existent-kid")
        
        assert "not found in JWKS" in str(exc_info.value)
    
    def test_cache_expiry(self, mock_jwks_client):
        """Test that cache expires after TTL."""
        client = JWKSClient()
        assert client._cache.ttl == settings.JWKS_CACHE_TTL
