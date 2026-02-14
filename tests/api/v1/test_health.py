"""Tests for health endpoint."""

import pytest
from app.core.config import settings


def test_health_check_returns_200(client):
    """Test health check endpoint returns 200 OK."""
    response = client.get(f"{settings.API_V1_STR}/health")
    assert response.status_code == 200


def test_health_check_response_schema(client):
    """Test health check response contains expected fields."""
    response = client.get(f"{settings.API_V1_STR}/health")
    data = response.json()
    
    assert "status" in data
    assert data["status"] == "ok"
    assert "project" in data
    assert data["project"] == settings.PROJECT_NAME
    assert "region" in data


def test_health_accessible_without_auth(client):
    """Test health endpoint is accessible without authentication."""
    # No Authorization header
    response = client.get(f"{settings.API_V1_STR}/health")
    assert response.status_code == 200
