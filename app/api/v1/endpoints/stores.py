from typing import List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, get_db
from app.schemas.response import ResponseModel
from app.schemas.store import StoreCreate, StoreResponse
from app.schemas.token import TokenPayload
from app.services.store_service import create_store, get_active_stores

router = APIRouter(prefix="/stores", tags=["stores"])


@router.get("", response_model=ResponseModel[List[StoreResponse]])
def list_stores(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ResponseModel[List[StoreResponse]]:
    stores = get_active_stores(db=db, skip=skip, limit=limit)
    serialized_stores = [
        StoreResponse.model_validate(store) for store in stores
    ]
    return ResponseModel(
        success=True,
        message="Active stores retrieved successfully",
        data=serialized_stores,
    )


@router.post(
    "",
    response_model=ResponseModel[StoreResponse],
    status_code=status.HTTP_201_CREATED,
)
def register_store(
    payload: StoreCreate,
    current_user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResponseModel[StoreResponse]:
    new_store = create_store(
        db=db,
        owner_id=current_user.user_id,
        data=payload,
    )
    return ResponseModel(
        success=True,
        message="Store registered successfully",
        data=StoreResponse.model_validate(new_store),
    )
