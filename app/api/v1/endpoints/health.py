from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()

@router.get("/health")
def health_check():
    """
    Health check endpoint.
    """
    return {
        "status": "ok",
        "project": settings.PROJECT_NAME,
        "region": settings.COGNITO_REGION
    }
