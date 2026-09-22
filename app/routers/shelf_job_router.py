from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, verify_store_access
from app.schemas.shelf_job_schema import ShelfJobCreateSchema, ShelfJobResponseSchema
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


router.router = router
