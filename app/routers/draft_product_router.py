import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.api.deps import get_db, verify_store_access
from app.models.product import StoreProduct
from app.models.shelf_job import DraftProduct
from app.schemas.draft_product_schema import (
    DraftProductApprovalResponseSchema,
    DraftProductBatchApproveSchema,
    DraftProductResponseSchema,
    DraftProductUpdateSchema,
)

router = APIRouter(prefix="/api/v1/stores", tags=["AI Draft Approvals & Review"])


@router.get(
    "/{store_id}/draft-products",
    response_model=List[DraftProductResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="List extracted AI draft products",
    description="Retrieve all AI-extracted draft products for review, with optional filters by job or status.",
)
def list_draft_products(
    store_id: str,
    shelf_job_id: Optional[str] = Query(default=None, description="Filter by shelf job ID"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="Filter by status (PENDING_REVIEW, APPROVED, REJECTED)"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> List[DraftProductResponseSchema]:
    query = db.query(DraftProduct).filter(DraftProduct.store_id == store_id)
    if shelf_job_id:
        query = query.filter(DraftProduct.shelf_job_id == shelf_job_id)
    if status_filter:
        query = query.filter(DraftProduct.status == status_filter.upper())

    drafts = query.offset(skip).limit(limit).all()
    return [DraftProductResponseSchema.model_validate(d) for d in drafts]


@router.get(
    "/{store_id}/draft-products/{draft_id}",
    response_model=DraftProductResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get single draft product details",
)
def get_draft_product(
    store_id: str,
    draft_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> DraftProductResponseSchema:
    draft = (
        db.query(DraftProduct)
        .filter(DraftProduct.id == draft_id, DraftProduct.store_id == store_id)
        .first()
    )
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft product '{draft_id}' not found",
        )
    return DraftProductResponseSchema.model_validate(draft)


@router.put(
    "/{store_id}/draft-products/{draft_id}",
    response_model=DraftProductResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Edit AI draft product details",
    description="Modify proposed name, price, barcode, category or location before approval.",
)
def update_draft_product(
    store_id: str,
    draft_id: str,
    payload: DraftProductUpdateSchema,
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> DraftProductResponseSchema:
    draft = (
        db.query(DraftProduct)
        .filter(DraftProduct.id == draft_id, DraftProduct.store_id == store_id)
        .first()
    )
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft product '{draft_id}' not found",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        if hasattr(draft, field):
            setattr(draft, field, val)

    draft.updated_at = func.now()
    db.commit()
    db.refresh(draft)
    return DraftProductResponseSchema.model_validate(draft)


def _convert_draft_to_store_product(db: Session, draft: DraftProduct) -> StoreProduct:
    """Helper to convert an approved DraftProduct into a live StoreProduct in the catalog."""
    sku = draft.barcode_detected or f"SKU-AI-{draft.id[:8].upper()}"
    map_target = f"{draft.zone or 'ZONE'}-{draft.aisle or '01'}"

    # Check if SKU already exists for this store
    existing_product = (
        db.query(StoreProduct)
        .filter(StoreProduct.store_id == draft.store_id, StoreProduct.store_sku == sku)
        .first()
    )

    if existing_product:
        existing_product.product_name = draft.proposed_name
        existing_product.price = draft.estimated_price
        existing_product.category = draft.category_hint or existing_product.category or "General"
        existing_product.barcode = draft.barcode_detected or existing_product.barcode
        existing_product.zone = draft.zone or existing_product.zone
        existing_product.aisle = draft.aisle or existing_product.aisle
        existing_product.rack = draft.rack or existing_product.rack
        existing_product.shelf = draft.shelf or existing_product.shelf
        existing_product.updated_at = func.now()
        product = existing_product
    else:
        product = StoreProduct(
            id=str(uuid.uuid4()),
            store_id=draft.store_id,
            store_sku=sku,
            barcode=draft.barcode_detected,
            product_name=draft.proposed_name,
            category=draft.category_hint or "General",
            price=draft.estimated_price,
            stock_status="IN_STOCK",
            quantity=1,
            zone=draft.zone or "Zone A",
            aisle=draft.aisle or "Aisle 1",
            rack=draft.rack,
            shelf=draft.shelf,
            map_target=map_target,
        )
        db.add(product)

    draft.status = "APPROVED"
    draft.updated_at = func.now()
    db.commit()
    db.refresh(product)
    return product


@router.post(
    "/{store_id}/draft-products/{draft_id}/approve",
    response_model=DraftProductApprovalResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Approve AI draft product into catalog",
    description="Promote an AI-extracted draft product to the live product catalog.",
)
def approve_draft_product(
    store_id: str,
    draft_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> DraftProductApprovalResponseSchema:
    draft = (
        db.query(DraftProduct)
        .filter(DraftProduct.id == draft_id, DraftProduct.store_id == store_id)
        .first()
    )
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft product '{draft_id}' not found",
        )

    product = _convert_draft_to_store_product(db, draft)
    return DraftProductApprovalResponseSchema(
        draft_id=draft.id,
        status="APPROVED",
        store_product_id=product.id,
        message="Draft product approved and added to live store catalog",
    )


@router.post(
    "/{store_id}/draft-products/{draft_id}/reject",
    response_model=DraftProductApprovalResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Reject AI draft product",
    description="Mark an AI draft product as rejected.",
)
def reject_draft_product(
    store_id: str,
    draft_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> DraftProductApprovalResponseSchema:
    draft = (
        db.query(DraftProduct)
        .filter(DraftProduct.id == draft_id, DraftProduct.store_id == store_id)
        .first()
    )
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft product '{draft_id}' not found",
        )

    draft.status = "REJECTED"
    draft.updated_at = func.now()
    db.commit()

    return DraftProductApprovalResponseSchema(
        draft_id=draft.id,
        status="REJECTED",
        store_product_id=None,
        message="Draft product rejected successfully",
    )


@router.post(
    "/{store_id}/draft-products/batch-approve",
    response_model=List[DraftProductApprovalResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="Batch approve AI draft products",
    description="Approve multiple draft products in a single operation.",
)
def batch_approve_draft_products(
    store_id: str,
    payload: DraftProductBatchApproveSchema,
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> List[DraftProductApprovalResponseSchema]:
    drafts = (
        db.query(DraftProduct)
        .filter(
            DraftProduct.store_id == store_id,
            DraftProduct.id.in_(payload.draft_ids),
        )
        .all()
    )

    results = []
    for draft in drafts:
        product = _convert_draft_to_store_product(db, draft)
        results.append(
            DraftProductApprovalResponseSchema(
                draft_id=draft.id,
                status="APPROVED",
                store_product_id=product.id,
                message="Draft product approved",
            )
        )

    return results


router.router = router
