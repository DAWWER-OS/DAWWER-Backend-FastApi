from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, verify_store_access
from app.models.shelf_job import ShelfJob
from app.schemas.draft_product_schema import DraftProductDeleteResponseSchema
from app.schemas.shelf_job_schema import (
    ShelfJobCreateSchema,
    ShelfJobDeleteResponseSchema,
    ShelfJobResponseSchema,
)
from app.services import shelf_job_service

router = APIRouter(prefix="/api/v1/stores", tags=["Shelf Jobs & Gemini AI Capture"])


@router.post(
    "/{store_id}/shelf-jobs",
    response_model=ShelfJobResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new shelf capture and AI extraction job",
)
async def create_shelf_job(
    store_id: str,
    file: UploadFile = File(...),
    zone: str = Form(...),
    aisle: str = Form(...),
    rack: Optional[str] = Form(None),
    shelf: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_store_access),
) -> ShelfJobResponseSchema:
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="صيغة الملف غير مدعومة. يرجى رفع صورة صالحة",
            

        )

    image_bytes = await file.read()
    location_in = ShelfJobCreateSchema(zone=zone, aisle=aisle, rack=rack, shelf=shelf)

    try:
        job = shelf_job_service.process_shelf_capture_job(
            db=db,
            store_id=store_id,
            location_in=location_in,
            image_bytes=image_bytes,
            filename=file.filename,
        )
        return job
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/{store_id}/shelf-jobs/{job_id}",
    response_model=ShelfJobResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get shelf job details by ID",
)
def get_shelf_job(
    store_id: str,
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_store_access),
) -> ShelfJobResponseSchema:
    job = shelf_job_service.get_shelf_job_by_id(db=db, store_id=store_id, job_id=job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shelf job not found",
        )
    return job


@router.get(
    "/{store_id}/shelf-jobs",
    response_model=List[ShelfJobResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="List store shelf jobs with pagination",
)
def list_store_shelf_jobs(
    store_id: str,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_store_access),
) -> List[ShelfJobResponseSchema]:
    return shelf_job_service.get_store_shelf_jobs(
        db=db, store_id=store_id, skip=skip, limit=limit
    )


@router.delete(
    "/{store_id}/shelf-jobs/{job_id}",
    response_model=ShelfJobDeleteResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Delete shelf job and associated image files",
)
def delete_shelf_job(
    store_id: str,
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_store_access),
) -> ShelfJobDeleteResponseSchema:
    job = shelf_job_service.get_shelf_job_by_id(db=db, store_id=store_id, job_id=job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shelf job not found",
        )

    success = shelf_job_service.delete_shelf_job(db=db, store_id=store_id, job_id=job_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shelf job not found",
        )

    return ShelfJobDeleteResponseSchema(
        message="Shelf job successfully deleted",
        job_id=str(job_id),
        id=str(job_id),
        product_id=str(job_id),
        store_id=str(store_id),
        deleted=True,
    )


@router.delete(
    "/{store_id}/shelf-jobs/{job_id}/items/{item_id}",
    response_model=DraftProductDeleteResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Delete single item from a shelf job",
)
def delete_shelf_job_item(
    store_id: str,
    job_id: str,
    item_id: str,
    hard_delete: bool = Query(default=True, description="Permanently delete from database if True, else soft-reject"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_store_access),
) -> DraftProductDeleteResponseSchema:
    is_hard_deleted, draft = shelf_job_service.delete_draft_product(
        db=db,
        store_id=store_id,
        draft_id=item_id,
        hard_delete=hard_delete,
    )
    if not is_hard_deleted and not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shelf job item '{item_id}' not found",
        )

    return DraftProductDeleteResponseSchema(
        message="Shelf job item permanently deleted" if is_hard_deleted else "Shelf job item rejected",
        draft_id=str(item_id),
        product_id=str(item_id),
        store_id=str(store_id),
        deleted=True,
        hard_deleted=is_hard_deleted,
    )


router.router = router

# Legacy Router for un-prefixed or deprecated paths:
# /stores/{store_id}/shelf-jobs/{job_id}
# /shelf/sessions/{id}
# /shelf/captures/{id}
legacy_router = APIRouter(tags=["Shelf Jobs & Gemini AI Capture (Legacy)"])


@legacy_router.delete(
    "/stores/{store_id}/shelf-jobs/{job_id}",
    response_model=ShelfJobDeleteResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Legacy delete shelf job under store path",
    include_in_schema=False,
)
def delete_shelf_job_legacy_store_path(
    store_id: str,
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_store_access),
) -> ShelfJobDeleteResponseSchema:
    return delete_shelf_job(store_id=store_id, job_id=job_id, db=db, current_user=current_user)


@legacy_router.delete(
    "/shelf/sessions/{id}",
    response_model=ShelfJobDeleteResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Legacy delete shelf session route",
)
@legacy_router.delete(
    "/shelf/captures/{id}",
    response_model=ShelfJobDeleteResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Legacy delete shelf capture route",
)
@legacy_router.delete(
    "/api/v1/shelf/sessions/{id}",
    response_model=ShelfJobDeleteResponseSchema,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@legacy_router.delete(
    "/api/v1/shelf/captures/{id}",
    response_model=ShelfJobDeleteResponseSchema,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def delete_shelf_job_legacy(
    id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ShelfJobDeleteResponseSchema:
    # 1. Look up shelf job by ID to discover store_id
    job = db.query(ShelfJob).filter(ShelfJob.id == id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shelf job not found",
        )

    # 2. Enforce BR-14 store isolation scoping
    verify_store_access(store_id=job.store_id, current_user=current_user, db=db)

    # 3. Safely delete job and files
    success = shelf_job_service.delete_shelf_job(db=db, store_id=job.store_id, job_id=job.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shelf job not found",
        )

    return ShelfJobDeleteResponseSchema(
        message="Shelf job successfully deleted",
        job_id=str(job.id),
        id=str(job.id),
        product_id=str(job.id),
        store_id=str(job.store_id),
        deleted=True,
    )


@legacy_router.get(
    "/shelf/sessions/{id}",
    response_model=ShelfJobResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Legacy get shelf session route",
)
@legacy_router.get(
    "/shelf/captures/{id}",
    response_model=ShelfJobResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Legacy get shelf capture route",
)
@legacy_router.get(
    "/api/v1/shelf/sessions/{id}",
    response_model=ShelfJobResponseSchema,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@legacy_router.get(
    "/api/v1/shelf/captures/{id}",
    response_model=ShelfJobResponseSchema,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def get_shelf_job_legacy(
    id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ShelfJobResponseSchema:
    job = db.query(ShelfJob).filter(ShelfJob.id == id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shelf job not found",
        )
    verify_store_access(store_id=job.store_id, current_user=current_user, db=db)
    return job
