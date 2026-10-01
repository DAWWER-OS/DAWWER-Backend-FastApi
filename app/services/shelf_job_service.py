import logging
import sys
import traceback
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.shelf_job import DraftProduct, ShelfJob
from app.models.store import Store
from app.schemas.shelf_job_schema import JobStatusEnum, ShelfJobCreateSchema
from app.services import gemini_service
from app.services.storage_service import delete_shelf_image, save_shelf_image

logger = logging.getLogger("daweros_api.shelf_job")

# Enum alias for ShelfJobStatus
ShelfJobStatus = JobStatusEnum


def process_shelf_capture_job(
    db: Session,
    store_id: str,
    location_in: ShelfJobCreateSchema,
    image_bytes: bytes,
    image_url: Optional[str] = None,
    filename: Optional[str] = None,
) -> ShelfJob:
    # 0. Validate Data Integrity: verify store_id exists
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"المتجر المطلوب غير موجود: {store_id}",
        )

    # 1. Save uploaded image to disk if image_url is not already provided
    saved_file_path: Optional[str] = None
    if not image_url and image_bytes:
        try:
            saved_file_path, image_url = save_shelf_image(
                store_id=store_id,
                raw_filename=filename,
                image_bytes=image_bytes,
            )
        except Exception as exc:
            logger.error("Failed to save shelf image: %s\n%s", exc, traceback.format_exc())
            print(
                f"\n[SHELF IMAGE SAVE ERROR] Failed to save shelf image for store {store_id}: {exc}\n{traceback.format_exc()}",
                file=sys.stderr,
                flush=True,
            )

    job = ShelfJob(
        store_id=store_id,
        status=ShelfJobStatus.PROCESSING.value,
        zone=location_in.zone,
        aisle=location_in.aisle,
        rack=location_in.rack,
        shelf=location_in.shelf,
        image_url=image_url,
    )
    db.add(job)
    try:
        db.commit()
        db.refresh(job)
    except Exception as exc:
        db.rollback()
        logger.error("Database commit error creating initial shelf job for store %s: %s", store_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error during shelf job creation: {str(exc)}",
        )

    # 2. Multimodal AI Analysis with Gemini
    try:
        extracted_items = gemini_service.analyze_shelf_image(image_bytes)

        draft_records = []
        for item in extracted_items:
            draft = DraftProduct(
                store_id=store_id,
                shelf_job_id=job.id,
                proposed_name=item.proposed_name,
                estimated_price=item.estimated_price or 0.0,
                category_hint=item.category_hint,
                pack_size=item.pack_size,
                barcode_detected=item.barcode_detected,
                confidence_score=item.confidence_score or 0.0,
                zone=location_in.zone,
                aisle=location_in.aisle,
                rack=location_in.rack,
                shelf=location_in.shelf,
            )
            draft_records.append(draft)

        if draft_records:
            db.add_all(draft_records)

        job.status = ShelfJobStatus.COMPLETED.value
        job.extracted_drafts_count = len(draft_records)
        job.error_message = None

        try:
            db.commit()
            db.refresh(job)
            logger.info(
                "Shelf job %s completed with status COMPLETED and %d draft products",
                job.id,
                len(draft_records),
            )
        except Exception as commit_exc:
            db.rollback()
            logger.error("Database commit error updating shelf job %s: %s", job.id, commit_exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to commit shelf job drafts: {str(commit_exc)}",
            )
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.error(
            "Shelf capture analysis failed for job %s (store %s): %s\n%s",
            job.id,
            store_id,
            exc,
            traceback.format_exc(),
        )
        print(
            f"\n[SHELF JOB AI FAILURE] Job {job.id} failed during Gemini analysis: {exc}\n{traceback.format_exc()}",
            file=sys.stderr,
            flush=True,
        )
        try:
            job_record = db.query(ShelfJob).filter(ShelfJob.id == job.id).first()
            if job_record:
                job_record.status = ShelfJobStatus.FAILED.value
                job_record.error_message = str(exc)
                job_record.extracted_drafts_count = 0
                db.commit()
                db.refresh(job_record)
                job = job_record
            else:
                job.status = ShelfJobStatus.FAILED.value
                job.error_message = str(exc)
                job.extracted_drafts_count = 0
                db.add(job)
                db.commit()
                db.refresh(job)
        except Exception as update_exc:
            db.rollback()
            logger.error("Failed to commit FAILED status for shelf job %s: %s", job.id, update_exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error updating shelf job to failed: {str(update_exc)}",
            )

    return job


def get_shelf_job_by_id(
    db: Session, store_id: str, job_id: str
) -> Optional[ShelfJob]:
    return (
        db.query(ShelfJob)
        .filter(
            ShelfJob.id == job_id,
            ShelfJob.store_id == store_id,
        )
        .first()
    )


def get_store_shelf_jobs(
    db: Session, store_id: str, skip: int = 0, limit: int = 50
) -> List[ShelfJob]:
    return (
        db.query(ShelfJob)
        .filter(ShelfJob.store_id == store_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def delete_shelf_job(db: Session, store_id: str, job_id: str) -> bool:
    """Deletes a shelf job record, its associated draft products, and cleans up uploaded image files."""
    job = (
        db.query(ShelfJob)
        .filter(
            ShelfJob.id == job_id,
            ShelfJob.store_id == store_id,
        )
        .first()
    )
    if not job:
        return False

    # 1. Safely remove associated image files from uploads/shelf_jobs/{store_id}/
    if job.image_url:
        delete_shelf_image(store_id=store_id, image_url=job.image_url)

    # 2. Clean up associated draft products
    db.query(DraftProduct).filter(
        DraftProduct.shelf_job_id == job.id,
        DraftProduct.store_id == store_id,
    ).delete(synchronize_session=False)

    # 3. Delete job record
    db.delete(job)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Database commit error deleting shelf job %s: %s", job_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error during shelf job deletion: {str(exc)}",
        )

    logger.info("Successfully deleted shelf job %s for store %s", job_id, store_id)
    return True
