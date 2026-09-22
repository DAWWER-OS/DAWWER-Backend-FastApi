from typing import Any, Callable, List, Optional
import uuid
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.store import Store
from app.models.store_rbac import StoreStaff
from app.schemas.token import TokenPayload

# Standard .NET / ASP.NET Identity claim URIs
DOTNET_NAME_IDENTIFIER_CLAIM = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"
DOTNET_ROLE_CLAIM = "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"
DOTNET_EMAIL_CLAIM = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"
DOTNET_NAME_CLAIM = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"

security_scheme = HTTPBearer(auto_error=False)


def verify_token(token: str) -> TokenPayload:
    """Decodes and validates JWT token, extracting user claims with full .NET Identity support."""
    payload: dict[str, Any] = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        issuer=settings.JWT_ISSUER,
        audience=settings.JWT_AUDIENCE,
        options={
            "require": ["exp", "iss", "aud"],
            "verify_exp": True,
            "verify_iss": True,
            "verify_aud": True,
        },
    )

    # 1. Parse user_id from standard and .NET Identity claims
    user_id = (
        payload.get(DOTNET_NAME_IDENTIFIER_CLAIM)
        or payload.get("sub")
        or payload.get("nameid")
        or payload.get("uid")
        or payload.get("userId")
        or payload.get("UserId")
    )

    if not user_id:
        raise ValueError("Token does not contain a valid user identifier")

    # 2. Parse role(s) from standard and .NET Identity claims
    raw_role = (
        payload.get(DOTNET_ROLE_CLAIM)
        or payload.get("role")
        or payload.get("roles")
        or payload.get("Role")
        or payload.get("http://schemas.microsoft.com/ws/2008/06/identity/claims/role")
    )

    roles: List[str] = []
    primary_role: Optional[str] = None

    if isinstance(raw_role, list):
        roles = [str(r) for r in raw_role if r]
        primary_role = roles[0] if roles else None
    elif raw_role is not None:
        primary_role = str(raw_role)
        roles = [primary_role]

    # 3. Parse store_id scoping claims
    store_id = (
        payload.get("store_id")
        or payload.get("storeId")
        or payload.get("StoreId")
        or payload.get("Store_Id")
        or payload.get("store")
        or payload.get("http://schemas.dawwer.com/identity/claims/storeid")
        or payload.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/storeid")
        or payload.get("urn:dawwer:store_id")
    )

    # 4. Parse email claim
    email = (
        payload.get(DOTNET_EMAIL_CLAIM)
        or payload.get("email")
        or payload.get("Email")
    )

    return TokenPayload(
        user_id=str(user_id),
        role=primary_role,
        roles=roles,
        store_id=str(store_id) if store_id is not None else None,
        email=str(email) if email is not None else None,
    )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> TokenPayload:
    """FastAPI dependency to extract and authenticate current user from Bearer JWT token."""
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return verify_token(credentials.credentials)
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or malformed token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_role(allowed_roles: List[str]) -> Callable[[TokenPayload], TokenPayload]:
    """Dependency factory restricting route access to specified roles (case-insensitive)."""
    def role_checker(
        current_user: TokenPayload = Depends(get_current_user),
    ) -> TokenPayload:
        user_roles = set()
        if current_user.role:
            user_roles.add(current_user.role.lower())
        for r in current_user.roles:
            user_roles.add(r.lower())

        allowed_normalized = {r.lower() for r in allowed_roles}
        if not user_roles.intersection(allowed_normalized):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted",
            )
        return current_user

    return role_checker


def is_valid_uuid(val: Any) -> bool:
    """Helper to verify if a string is a valid UUID representation."""
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def verify_store_access(
    store_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TokenPayload:
    """Enforces BR-14 Store Scoping and Isolation.

    Grants access if:
    1. User has an Admin/SuperAdmin role (platform-level administrative bypass).
    2. Target store exists, and:
       a. User is the store owner (store.owner_id == current_user.user_id).
       b. User token explicitly bears matching store_id claim.
       c. User is registered as an Active staff member for this store in `store_staff`.

    Raises:
    - 400 Bad Request if store_id is empty.
    - 404 Not Found if store does not exist.
    - 403 Forbidden if user fails store isolation scoping.
    """
    if not store_id or not store_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid store identifier provided",
        )

    # Fast validation: if store_id is not a valid UUID format, Store cannot exist in PostgreSQL
    if not is_valid_uuid(store_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store '{store_id}' not found",
        )

    target_store = db.query(Store).filter(Store.id == store_id).first()
    if not target_store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store '{store_id}' not found",
        )

    # 1. Platform Admin bypass
    if current_user.is_admin():
        return current_user

    # 2. Store Owner match
    if str(target_store.owner_id).lower() == str(current_user.user_id).lower():
        return current_user

    # 3. Direct JWT claim match
    if current_user.store_id and str(current_user.store_id).lower() == str(target_store.id).lower():
        return current_user

    # 4. Store Staff verification (safely query only if user_id is a valid UUID)
    if is_valid_uuid(current_user.user_id):
        staff_member = (
            db.query(StoreStaff)
            .filter(
                StoreStaff.store_id == target_store.id,
                StoreStaff.user_id == current_user.user_id,
                StoreStaff.status == "Active",
            )
            .first()
        )
        if staff_member:
            return current_user

    # Failure: Forbidden under BR-14 isolation
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Operation not permitted: Access denied under BR-14 store isolation policy",
    )
