"""Integration tests for Cognito OAuth2 flow."""

import pytest
from fastapi.testclient import TestClient
from app.core.config import settings
from unittest.mock import patch, MagicMock

class TestCognitoOAuth2Flow:
    """Integration tests for Cognito OAuth2 endpoints."""
    
    @pytest.fixture(autouse=True)
    def setup_test_mode(self, override_settings):
        """Ensure testing mode is enabled for all tests in this class."""
        override_settings(TESTING_MODE=True)
    
    def test_login_redirect(self, client):

        """Test that /login redirects to Cognito with correct parameters."""
        response = client.get(f"{settings.API_V1_STR}/auth/login", follow_redirects=False)
        
        assert response.status_code == 307
        location = response.headers["location"]
        assert f"https://{settings.COGNITO_DOMAIN}/oauth2/authorize" in location
        assert "response_type=code" in location
        assert f"client_id={settings.COGNITO_APP_CLIENT_ID}" in location
        assert f"redirect_uri={settings.COGNITO_REDIRECT_URI}" in location
        assert "state=" in location
        assert "code_challenge=" in location
        assert "code_challenge_method=S256" in location
        
        # Verify cookies are set
        assert "auth_state" in response.cookies
        assert "code_verifier" in response.cookies

    
    @patch("requests.post")
    def test_callback_success(self, mock_post, client):
        """Test successful callback processing."""
        # Mock successful token exchange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "mock_access_token",
            "id_token": "mock_id_token",
            "refresh_token": "mock_refresh_token",
            "expires_in": 3600,
            "token_type": "Bearer"
        }
        mock_post.return_value = mock_response
        
        # Setup cookies matches the state we pass
        state = "test_state"
        code_verifier = "test_verifier"
        client.cookies.set("auth_state", state)
        client.cookies.set("code_verifier", code_verifier)
        
        response = client.get(
            f"{settings.API_V1_STR}/auth/callback",
            params={"code": "test_code", "state": state}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "mock_access_token"
        assert data["id_token"] == "mock_id_token"
        
        # Verify cookies are cleared
        assert "auth_state" not in response.cookies
        assert "code_verifier" not in response.cookies
    
    def test_callback_invalid_state(self, client):
        """Test callback with invalid state parameter."""
        client.cookies.set("auth_state", "correct_state")
        
        response = client.get(
            f"{settings.API_V1_STR}/auth/callback",
            params={"code": "test_code", "state": "wrong_state"}
        )
        
        assert response.status_code == 400
        assert "Invalid state parameter" in response.json()["detail"]
