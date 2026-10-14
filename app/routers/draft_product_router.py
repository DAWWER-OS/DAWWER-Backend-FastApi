import json
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.api.deps import get_db, verify_store_access
from app.models.product import StoreProduct
from app.models.scan_job import ScanJob
from app.models.shelf_job import DraftProduct, ShelfJob
from app.schemas.draft_product_schema import (
    DraftProductApprovalResponseSchema,
    DraftProductBatchApproveSchema,
    DraftProductDeleteResponseSchema,
    DraftProductResponseSchema,
    DraftProductUpdateSchema,
    ProductDraftJobDetailsResponseSchema,
)
from app.services import shelf_job_service

router = APIRouter(prefix="/api/v1/stores", tags=["AI Draft Approvals & Review"])


@router.get(
    "/{store_id}/product-drafts/{job_id}",
    response_model=ProductDraftJobDetailsResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get product draft details and status by job ID",
    description="Retrieve extraction details, warning flags, and localized guidance messages for a shelf scan job under BR-17.",
)
def get_product_drafts_by_job(
    store_id: str,
    job_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> ProductDraftJobDetailsResponseSchema:
    # 1. Look up ShelfJob by job_id
    shelf_job = (
        db.query(ShelfJob)
        .filter(ShelfJob.id == job_id, ShelfJob.store_id == store_id)
        .first()
    )

    # 2. Look up ScanJob by job_id if not directly matching a shelf job
    scan_job = None
    if not shelf_job:
        scan_job = (
            db.query(ScanJob)
            .filter(ScanJob.id == job_id, ScanJob.store_id == store_id)
            .first()
        )
        if scan_job and scan_job.shelf_job_id:
            shelf_job = (
                db.query(ShelfJob)
                .filter(ShelfJob.id == scan_job.shelf_job_id, ShelfJob.store_id == store_id)
                .first()
            )

    if not shelf_job and not scan_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product drafts job '{job_id}' not found",
        )

    # 3. Retrieve draft products
    drafts = []
    if shelf_job:
        drafts = (
            db.query(DraftProduct)
            .filter(DraftProduct.shelf_job_id == shelf_job.id, DraftProduct.store_id == store_id)
            .all()
        )

    products_count = len(drafts)
    status_str = shelf_job.status if shelf_job else (scan_job.status if scan_job else "PROCESSING")

    # 4. Extract warning metadata
    has_warning = False
    warning_code = None
    user_message = None

    if shelf_job and shelf_job.error_message:
        try:
            meta = json.loads(shelf_job.error_message)
            if isinstance(meta, dict):
                has_warning = meta.get("has_warning", False) or "warning" in meta or "warning_code" in meta
                warning_code = meta.get("warning_code") or meta.get("warning") or meta.get("code")
                user_message = meta.get("user_message") or meta.get("message")
        except Exception:
            if "NO_PRODUCTS_FOUND" in shelf_job.error_message:
                has_warning = True
                warning_code = "NO_PRODUCTS_FOUND"
                user_message = "لم يتعرف النظام على أي منتجات تجارية في هذه الصورة. يرجى التأكد من توجيه الكاميرا لرف حقيقي ومضاء جيداً."

    # If products_count == 0 and status is REVIEW_REQUIRED (or 0 products detected)
    if products_count == 0 and (status_str == "REVIEW_REQUIRED" or (shelf_job and shelf_job.extracted_drafts_count == 0)):
        has_warning = True
        warning_code = warning_code or "NO_PRODUCTS_FOUND"
        user_message = user_message or "لم يتعرف النظام على أي منتجات تجارية في هذه الصورة. يرجى التأكد من توجيه الكاميرا لرف حقيقي ومضاء جيداً."

    metadata = {
        "warning": warning_code,
        "warning_code": warning_code,
        "user_message": user_message,
        "products_count": products_count,
        "status": status_str,
    } if has_warning else None

    resolved_id = shelf_job.id if shelf_job else (scan_job.id if scan_job else job_id)

    response_dict = {
        "id": resolved_id,
        "job_id": job_id,
        "jobId": job_id,
        "store_id": store_id,
        "storeId": store_id,
        "status": status_str,
        "products_count": products_count,
        "productsCount": products_count,
        "has_warning": has_warning,
        "hasWarning": has_warning,
        "warning_code": warning_code,
        "warningCode": warning_code,
        "user_message": user_message,
        "userMessage": user_message,
        "warning": warning_code,
        "message": user_message,
        "products": [DraftProductResponseSchema.model_validate(d) for d in drafts],
        "metadata": metadata,
        "created_at": shelf_job.created_at if shelf_job else (scan_job.created_at if scan_job else None),
        "updated_at": shelf_job.updated_at if shelf_job else (scan_job.updated_at if scan_job else None),
    }
    return ProductDraftJobDetailsResponseSchema(**response_dict)


@router.get(
    "/{store_id}/product-drafts",
    response_model=List[DraftProductResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="List extracted AI draft products (alias)",
    include_in_schema=False,
)
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
    include_rejected: bool = Query(default=False, description="Set True to include rejected draft products"),
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
    elif not include_rejected:
        query = query.filter(DraftProduct.status != "REJECTED")

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
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error rejecting draft product: {str(exc)}",
        )

    return DraftProductApprovalResponseSchema(
        draft_id=draft.id,
        product_id=str(draft.id),
        status="REJECTED",
        store_product_id=None,
        message="Draft product rejected successfully",
        deleted=True,
    )


@router.delete(
    "/{store_id}/draft-products/{draft_id}",
    response_model=DraftProductDeleteResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Delete extracted AI draft product",
    description="Permanently delete or reject an AI-extracted shelf item.",
)
def delete_draft_product_endpoint(
    store_id: str,
    draft_id: str,
    hard_delete: bool = Query(default=True, description="Permanently delete from database if True, else soft-reject"),
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> DraftProductDeleteResponseSchema:
    is_hard_deleted, draft = shelf_job_service.delete_draft_product(
        db=db,
        store_id=store_id,
        draft_id=draft_id,
        hard_delete=hard_delete,
    )
    if not is_hard_deleted and not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft product '{draft_id}' not found",
        )

    return DraftProductDeleteResponseSchema(
        message="Draft product item permanently deleted" if is_hard_deleted else "Draft product item rejected",
        draft_id=str(draft_id),
        product_id=str(draft_id),
        store_id=str(store_id),
        deleted=True,
        hard_deleted=is_hard_deleted,
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
