from typing import Any, Optional
import jwt
from app.core.config import settings
from app.schemas.token import TokenPayload

DOTNET_NAME_IDENTIFIER_CLAIM = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"
DOTNET_ROLE_CLAIM = "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"


def verify_token(token: str) -> TokenPayload:
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

    user_id = (
        payload.get(DOTNET_NAME_IDENTIFIER_CLAIM)
        or payload.get("sub")
        or payload.get("nameid")
    )

    if not user_id:
        raise ValueError("Token does not contain a valid user identifier")

    role = (
        payload.get(DOTNET_ROLE_CLAIM)
        or payload.get("role")
        or payload.get("roles")
    )

    store_id = (
        payload.get("store_id")
        or payload.get("storeId")
        or payload.get("StoreId")
    )

    return TokenPayload(
        user_id=str(user_id),
        role=str(role) if role is not None else None,
        store_id=str(store_id) if store_id is not None else None,
    )
