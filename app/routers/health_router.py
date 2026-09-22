from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["System Health"])


@router.get(
    "/health",
    summary="System Health & Database Probe",
    description="Perform a lightweight connectivity probe on the PostgreSQL database.",
    status_code=status.HTTP_200_OK,
    response_model=Dict[str, str],
)
@router.get(
    "/api/v1/health",
    summary="System Health & Database Probe (API v1)",
    description="Perform a lightweight connectivity probe on the PostgreSQL database.",
    status_code=status.HTTP_200_OK,
    response_model=Dict[str, str],
)
def check_health(db: Session = Depends(get_db)) -> Dict[str, str]:
    """Lightweight database connectivity health check."""
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected",
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "database": "unreachable",
                "error": str(exc),
            },
        )


router.router = router

__all__ = ["router", "check_health"]
