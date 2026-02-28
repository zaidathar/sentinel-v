from fastapi import APIRouter
from app.api.v1.endpoints import health, profile, auth, upload

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(profile.router, tags=["profile"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(upload.router, prefix="/upload", tags=["upload"])

