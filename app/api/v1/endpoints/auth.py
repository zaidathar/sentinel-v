"""Authentication endpoints for Cognito OAuth2 flow."""

import requests
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import RedirectResponse
from pydantic import Field

from app.core.config import settings
from app.core import security
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/login")
async def login():
    """
    Initiate Cognito OAuth2 login flow with PKCE.
    
    Generates state and PKCE verifier/challenge and redirects to Cognito.
    """
    state = security.generate_state()
    code_verifier, code_challenge = security.generate_pkce_pair()
    
    cognito_login_url = (
        f"https://{settings.COGNITO_DOMAIN}/oauth2/authorize?"
        f"response_type=code&"
        f"client_id={settings.COGNITO_APP_CLIENT_ID}&"
        f"redirect_uri={settings.COGNITO_REDIRECT_URI}&"
        f"state={state}&"
        f"code_challenge={code_challenge}&"
        f"code_challenge_method=S256"
    )
    
    logger.info("initiating_cognito_login", state=state)
    
    redirect_response = RedirectResponse(url=cognito_login_url)
    
    # Store state and code_verifier in secure HttpOnly cookies
    redirect_response.set_cookie(
        key="auth_state",
        value=state,
        httponly=True,
        secure=not settings.TESTING_MODE,
        samesite="lax",
        max_age=300  # 5 minutes
    )
    redirect_response.set_cookie(
        key="code_verifier",
        value=code_verifier,
        httponly=True,
        secure=not settings.TESTING_MODE,
        samesite="lax",
        max_age=300
    )
    logger.info("redirect_response", redirect_response=redirect_response)
    return redirect_response


@router.get("/callback")
async def callback(
    request: Request,
    response: Response,
    code: str,
    state: str
):
    """
    OAuth2 callback handler.
    
    Validates state, exchanges code for tokens using PKCE verifier.
    """
    logger.info("callback_received", code=code, state=state)
    stored_state = request.cookies.get("auth_state")
    code_verifier = request.cookies.get("code_verifier")
    
    if not stored_state or state != stored_state:
        logger.warning("invalid_state", state=state, stored_state=stored_state)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter"
        )
    
    if not code_verifier:
        logger.warning("missing_code_verifier")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing code verifier"
        )
    
    # Exchange code for tokens
    token_url = f"https://{settings.COGNITO_DOMAIN}/oauth2/token"
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.COGNITO_APP_CLIENT_ID,
        "code": code,
        "redirect_uri": settings.COGNITO_REDIRECT_URI,
        "code_verifier": code_verifier
    }
    
    # Include client secret if configured
    auth = None
    if settings.COGNITO_CLIENT_SECRET:
        auth = (settings.COGNITO_APP_CLIENT_ID, settings.COGNITO_CLIENT_SECRET)
    
    try:
        token_response = requests.post(
            token_url,
            data=data,
            auth=auth,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        token_response.raise_for_status()
        tokens = token_response.json()
    except requests.RequestException as e:
        error_detail = str(e)
        if e.response is not None:
            try:
                error_detail = e.response.json()
            except Exception:
                error_detail = e.response.text
        
        logger.error("token_exchange_failed", error=error_detail, status_code=e.response.status_code if e.response is not None else None)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token exchange failed: {error_detail}"
        )

    
    # Clear auth cookies
    response.delete_cookie("auth_state")
    response.delete_cookie("code_verifier")
    
    logger.info("token_exchange_successful")
    
    return {
        "access_token": tokens.get("access_token"),
        "id_token": tokens.get("id_token"),
        "refresh_token": tokens.get("refresh_token"),
        "expires_in": tokens.get("expires_in"),
        "token_type": tokens.get("token_type")
    }
