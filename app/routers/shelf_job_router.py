from typing import List, Optional
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, verify_store_access
from app.models.shelf_job import ShelfJob
from app.schemas.ai_quota_schema import ScanJobAcceptedResponseSchema
from app.schemas.draft_product_schema import DraftProductDeleteResponseSchema
from app.schemas.shelf_job_schema import (
    ShelfJobCreateSchema,
    ShelfJobDeleteResponseSchema,
    ShelfJobResponseSchema,
)
from app.schemas.token import TokenPayload
from app.services import (
    ai_quota_service,
    image_validation_service,
    shelf_job_service,
)
from app.services.shelf_extraction_worker import (
    process_gemini_vision_bg,
    process_shelf_extraction_async,
)

router = APIRouter(prefix="/api/v1/stores", tags=["Shelf Jobs & Gemini AI Capture"])


@router.post(
    "/{store_id}/shelves/extract-async",
    response_model=ScanJobAcceptedResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Asynchronous AI shelf capture and quota-managed product extraction",
    description="Validates image payload, verifies quota reservation under BR-14 tenant isolation, and enqueues background Gemini extraction.",
)
async def extract_shelf_async(
    store_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    zone: str = Form("A"),
    aisle: str = Form("1"),
    rack: Optional[str] = Form(None),
    shelf: Optional[str] = Form(None),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    idempotency_key_header: Optional[str] = Header(None, alias="Idempotency-Key"),
    idempotency_key_form: Optional[str] = Form(None, alias="idempotency_key"),
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(verify_store_access),
) -> ScanJobAcceptedResponseSchema:
    # 1. Strict Pre-Lock Image Validation (bounded chunked read, magic signature check, Pillow verify)
    image_bytes, _ = await image_validation_service.validate_image_upload(file)

    # 2. Resolve optional idempotency key
    idempotency_key = x_idempotency_key or idempotency_key_header or idempotency_key_form

    # 3. Atomic Quota Check & Reservation Transaction (with SELECT ... FOR UPDATE)
    job, is_replay = ai_quota_service.reserve_scan_quota(
        db=db,
        store_id=store_id,
        idempotency_key=idempotency_key,
    )

    # 4. Enqueue background processing if newly created or pending replay
    location_in = ShelfJobCreateSchema(zone=zone, aisle=aisle, rack=rack, shelf=shelf)
    if not is_replay or job.status == "PENDING":
        background_tasks.add_task(
            process_gemini_vision_bg,
            job_id=str(job.id),
            store_id=store_id,
            image_bytes=image_bytes,
            location_in=location_in,
            filename=file.filename,
        )

    return ScanJobAcceptedResponseSchema(
        job_id=str(job.id),
        store_id=str(job.store_id),
        status=job.status,
        created_at=job.created_at,
        message="Scan job accepted for processing" if not is_replay else f"Existing scan job returned ({job.status})",
        idempotency_key=job.idempotency_key,
    )


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
