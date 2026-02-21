"""Application configuration with production-grade settings."""

from typing import Optional
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Production-ready application settings."""
    
    PROJECT_NAME: str = "Sentinel-V"
    API_V1_STR: str = "/api/v1"
    
    COGNITO_REGION: str = Field(
        ...,
        description="AWS region where Cognito user pool is located (e.g., us-east-1)"
    )
    COGNITO_USER_POOL_ID: str = Field(
        ...,
        description="AWS Cognito User Pool ID (e.g., us-east-1_XXXXXXXXX)"
    )
    COGNITO_APP_CLIENT_ID: str = Field(
        ...,
        description="AWS Cognito App Client ID for JWT audience validation"
    )
    COGNITO_DOMAIN: str = Field(
        default="",
        description="AWS Cognito Domain (e.g., your-domain.auth.us-east-1.amazoncognito.com)"
    )
    COGNITO_REDIRECT_URI: str = Field(
        default="",
        description="OAuth2 callback URL"
    )

    COGNITO_CLIENT_SECRET: Optional[str] = Field(
        None,
        description="AWS Cognito App Client Secret (if applicable)"
    )

    
    JWKS_CACHE_TTL: int = Field(
        default=300,
        description="Time-to-live for JWKS cache in seconds (default: 5 minutes)"
    )
    
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    
    TESTING_MODE: bool = Field(
        default=False,
        description="Enable testing mode (allows mock tokens)"
    )
    
    @computed_field  # type: ignore[misc]
    @property
    def COGNITO_JWKS_URL(self) -> str:
        """Construct the JWKS URL from user pool configuration."""
        return (
            f"https://cognito-idp.{self.COGNITO_REGION}.amazonaws.com/"
            f"{self.COGNITO_USER_POOL_ID}/.well-known/jwks.json"
        )
    
    @computed_field  # type: ignore[misc]
    @property
    def COGNITO_ISSUER(self) -> str:
        """Expected issuer for JWT validation."""
        return (
            f"https://cognito-idp.{self.COGNITO_REGION}.amazonaws.com/"
            f"{self.COGNITO_USER_POOL_ID}"
        )
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
