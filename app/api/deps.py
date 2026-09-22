"""API dependencies module re-exporting core security dependencies for backwards compatibility."""

from typing import Callable, List, Optional
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import (
    get_current_user,
    require_role,
    security_scheme,
    verify_store_access,
    verify_token,
)
from app.db.session import get_db
from app.schemas.token import TokenPayload

__all__ = [
    "security_scheme",
    "get_current_user",
    "require_role",
    "verify_store_access",
    "verify_token",
    "get_db",
    "TokenPayload",
]
