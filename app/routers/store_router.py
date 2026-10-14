from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, verify_store_access
from app.models.store import Store
from app.schemas.ai_quota_schema import AIQuotaResponseSchema
from app.schemas.store_schema import StoreResponseSchema
from app.schemas.token import TokenPayload
from app.services import ai_quota_service, store_service

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


@router.get(
    "/{store_id}/ai-quota",
    response_model=AIQuotaResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get store AI scan quota summary",
    description="Retrieves current AI scan usage, limit, remaining scans, and rolling reset date under BR-14 authorization.",
)
def get_store_ai_quota(
    store_id: str,
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(verify_store_access),
) -> AIQuotaResponseSchema:
    # Verify store active status
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store '{store_id}' not found",
        )
    if not store.is_active or (store.status and store.status.upper() != "APPROVED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Store is inactive or pending approval",
        )

    return ai_quota_service.get_effective_quota(db=db, store_id=store_id)


# Export router and security dependency for BR-14 store isolation
router.router = router

__all__ = ["router", "verify_store_access", "get_store", "get_store_ai_quota"]
