from typing import List
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, verify_store_access
from app.schemas.import_schema import BulkImportSummaryResponse
from app.schemas.product_schema import (
    ProductCreateSchema,
    ProductDeleteResponseSchema,
    ProductResponseSchema,
    ProductUpdateSchema,
)
from app.services.bulk_import_service import (
    create_import_job,
    save_bulk_import_results,
)
from app.services.pandas_importer import process_bulk_catalog_file
from app.services.product_service import (
    create_product,
    delete_product,
    get_product_by_id,
    get_store_products,
    update_product,
)

router = APIRouter(prefix="/api/v1/stores", tags=["Products & Catalog Bulk Import"])


@router.post(
    "/{store_id}/products",
    response_model=ProductResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new product manually",
)
def create_store_product(
    store_id: str,
    product_in: ProductCreateSchema,
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> ProductResponseSchema:
    try:
        return create_product(db=db, store_id=store_id, product_in=product_in)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.put(
    "/{store_id}/products/{product_id}",
    response_model=ProductResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Update an existing product",
)
def update_store_product(
    store_id: str,
    product_id: str,
    product_in: ProductUpdateSchema,
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> ProductResponseSchema:
    product = update_product(
        db=db,
        store_id=store_id,
        product_id=product_id,
        product_in=product_in,
    )
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return product


@router.get(
    "/{store_id}/products/{product_id}",
    response_model=ProductResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get single product details",
)
def get_store_product(
    store_id: str,
    product_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> ProductResponseSchema:
    product = get_product_by_id(db=db, store_id=store_id, product_id=product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return product


@router.delete(
    "/{store_id}/products/{product_id}",
    response_model=ProductDeleteResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Delete or deactivate product",
    description="Soft-deactivates product (BR-15) and its associated locations by default, or permanently deletes if hard_delete=True.",
)
def delete_store_product(
    store_id: str,
    product_id: str,
    hard_delete: bool = Query(default=False, description="Set True for hard delete, False for soft deactivation"),
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> ProductDeleteResponseSchema:
    try:
        is_hard_deleted, product = delete_product(
            db=db,
            store_id=store_id,
            product_id=product_id,
            hard_delete=hard_delete,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )

    if is_hard_deleted:
        return ProductDeleteResponseSchema(
            message="Product permanently deleted",
            product_id=product_id,
            store_id=store_id,
            is_active=False,
            hard_deleted=True,
            product=None,
        )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    return ProductDeleteResponseSchema(
        message="Product successfully deactivated",
        product_id=product.id,
        store_id=product.store_id,
        is_active=product.is_active,
        hard_deleted=False,
        product=ProductResponseSchema.model_validate(product),
    )


@router.get(
    "/{store_id}/products",
    response_model=List[ProductResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="List store products with pagination",
)
def list_store_products(
    store_id: str,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> List[ProductResponseSchema]:
    return get_store_products(db=db, store_id=store_id, skip=skip, limit=limit)


@router.post(
    "/{store_id}/catalog/bulk-import",
    response_model=BulkImportSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk import catalog from CSV/Excel",
    description="Upload CSV or Excel file to batch import products into store catalog.",
)
async def bulk_import_catalog(
    store_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> BulkImportSummaryResponse:
    contents = await file.read()
    filename = file.filename or "unknown"

    job = create_import_job(db, store_id, filename)

    try:
        summary = process_bulk_catalog_file(contents, filename)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    save_bulk_import_results(db, job.id, store_id, summary)

    return BulkImportSummaryResponse(
        job_id=job.id,
        store_id=store_id,
        filename=filename,
        total_processed=summary["total_processed"],
        valid_count=summary["valid_count"],
        error_count=summary["error_count"],
        valid_records=summary["valid_records"],
        errors=summary["errors"],
    )


router.router = router
