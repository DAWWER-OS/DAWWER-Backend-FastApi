from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, get_db
from app.schemas.response import ResponseModel
from app.schemas.token import TokenPayload
from app.schemas.user import UserProfileResponse, UserProfileUpdate
from app.services.user_service import get_profile, update_profile

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me", response_model=ResponseModel[UserProfileResponse])
def read_my_profile(
    current_user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResponseModel[UserProfileResponse]:
    user = get_profile(db=db, user_id=current_user.user_id)
    return ResponseModel(
        success=True,
        message="User profile retrieved successfully",
        data=UserProfileResponse.model_validate(user),
    )


@router.put("/me", response_model=ResponseModel[UserProfileResponse])
def update_my_profile(
    payload: UserProfileUpdate,
    current_user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResponseModel[UserProfileResponse]:
    updated_user = update_profile(
        db=db,
        user_id=current_user.user_id,
        data=payload,
    )
    return ResponseModel(
        success=True,
        message="User profile updated successfully",
        data=UserProfileResponse.model_validate(updated_user),
    )
