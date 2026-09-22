from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, verify_store_access
from app.schemas.store_schema import StoreResponseSchema
from app.services import store_service

router = APIRouter(prefix="/api/v1/stores", tags=["Stores & JWT Security Dependencies"])


@router.get(
    "/{store_id}",
    response_model=StoreResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get store by ID",
    description="Retrieve detailed store profile by ID. Admin governance and merchant registrations are handled by .NET Core.",
)
def get_store(
    store_id: str,
    db: Session = Depends(get_db),
) -> StoreResponseSchema:
    store = store_service.get_store_by_id(db=db, store_id=store_id)
    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store '{store_id}' not found",
        )
    return StoreResponseSchema.model_validate(store)


# Export router and security dependency for BR-14 store isolation
router.router = router

__all__ = ["router", "verify_store_access", "get_store"]
