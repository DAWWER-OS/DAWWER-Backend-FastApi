from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.api.deps import get_db, require_role
from app.schemas.response import ResponseModel
from app.schemas.store import StoreResponse, StoreStatusUpdate
from app.schemas.token import TokenPayload
from app.services.store_service import get_pending_stores, update_store_status

router = APIRouter(prefix="/stores", tags=["admin-stores"])


@router.get("/pending", response_model=ResponseModel[List[StoreResponse]])
def read_pending_stores(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: TokenPayload = Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
) -> ResponseModel[List[StoreResponse]]:
    stores = get_pending_stores(db=db, skip=skip, limit=limit)
    serialized_stores = [
        StoreResponse.model_validate(store) for store in stores
    ]
    return ResponseModel(
        success=True,
        message="Pending stores retrieved successfully",
        data=serialized_stores,
    )


@router.patch("/{store_id}/status", response_model=ResponseModel[StoreResponse])
def change_store_status(
    store_id: str,
    payload: StoreStatusUpdate,
    current_user: TokenPayload = Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
) -> ResponseModel[StoreResponse]:
    updated_store = update_store_status(
        db=db,
        store_id=store_id,
        new_status=payload.status,
    )
    return ResponseModel(
        success=True,
        message="Store status updated successfully",
        data=StoreResponse.model_validate(updated_store),
    )
