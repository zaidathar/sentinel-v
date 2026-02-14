"""JWKS key management for AWS Cognito JWT verification."""

import requests
import structlog
from typing import Dict, Any
from cachetools import TTLCache
from app.core.config import settings
from app.core.exceptions import JWKSFetchError

logger = structlog.get_logger(__name__)


class JWKSClient:
    """Manages fetching and caching of JWKS keys from AWS Cognito."""
    
    def __init__(self):
        """Initialize JWKS client with TTL cache."""
        self._cache: TTLCache = TTLCache(
            maxsize=10,
            ttl=settings.JWKS_CACHE_TTL
        )
        logger.info(
            "jwks_client_initialized",
            cache_ttl=settings.JWKS_CACHE_TTL,
            jwks_url=settings.COGNITO_JWKS_URL
        )
    
    def get_signing_key(self, kid: str) -> Dict[str, Any]:
        """
        Get the signing key for a given key ID (kid).
        
        Args:
            kid: The key ID from the JWT header
            
        Returns:
            The JWK (JSON Web Key) dictionary
            
        Raises:
            JWKSFetchError: If fetching keys fails or kid not found
        """
        if kid in self._cache:
            logger.debug("jwks_cache_hit", kid=kid)
            return self._cache[kid]
        
        logger.debug("jwks_cache_miss", kid=kid)
        
        try:
            response = requests.get(
                settings.COGNITO_JWKS_URL,
                timeout=5
            )
            response.raise_for_status()
            jwks = response.json()
        except requests.RequestException as e:
            logger.error(
                "jwks_fetch_failed",
                error=str(e),
                url=settings.COGNITO_JWKS_URL
            )
            raise JWKSFetchError(f"Failed to fetch JWKS: {e}")
        
        if "keys" not in jwks:
            logger.error("jwks_invalid_structure", jwks=jwks)
            raise JWKSFetchError("Invalid JWKS response: missing 'keys' field")
        
        for key in jwks["keys"]:
            key_id = key.get("kid")
            if key_id:
                self._cache[key_id] = key
                logger.debug("jwks_key_cached", kid=key_id)
        
        if kid not in self._cache:
            logger.error("jwks_kid_not_found", kid=kid, available_kids=list(self._cache.keys()))
            raise JWKSFetchError(f"Key ID '{kid}' not found in JWKS")
        
        return self._cache[kid]


jwks_client = JWKSClient()
