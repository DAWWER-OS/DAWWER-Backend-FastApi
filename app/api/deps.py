from typing import Callable, List, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from app.core.security import verify_token
from app.db.session import get_db
from app.schemas.token import TokenPayload

security_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> TokenPayload:
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
    def role_checker(
        current_user: TokenPayload = Depends(get_current_user),
    ) -> TokenPayload:
        if not current_user.role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted",
            )

        allowed_normalized = {r.lower() for r in allowed_roles}
        if (
            current_user.role not in allowed_roles
            and current_user.role.lower() not in allowed_normalized
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted",
            )
        return current_user

    return role_checker

