from fastapi import APIRouter, Depends
from app.api.deps import get_current_user, require_role
from app.schemas.token import TokenPayload

router = APIRouter(prefix="/test-auth", tags=["test-auth"])


@router.get("/me", response_model=TokenPayload)
def read_current_user(
    current_user: TokenPayload = Depends(get_current_user),
) -> TokenPayload:
    return current_user


@router.get("/admin-only")
def read_admin_data(
    current_user: TokenPayload = Depends(require_role(["Admin", "admin"])),
) -> dict[str, str]:
    return {"message": "Access granted to admin route"}
