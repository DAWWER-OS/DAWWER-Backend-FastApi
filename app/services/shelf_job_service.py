import logging
import sys
import traceback
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.shelf_job import DraftProduct, ShelfJob
from app.schemas.shelf_job_schema import JobStatusEnum, ShelfJobCreateSchema
from app.services import gemini_service
from app.services.storage_service import save_shelf_image

logger = logging.getLogger("daweros_api.shelf_job")


def process_shelf_capture_job(
    db: Session,
    store_id: str,
    location_in: ShelfJobCreateSchema,
    image_bytes: bytes,
    image_url: Optional[str] = None,
    filename: Optional[str] = None,
) -> ShelfJob:
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
        status=JobStatusEnum.PROCESSING.value,
        zone=location_in.zone,
        aisle=location_in.aisle,
        rack=location_in.rack,
        shelf=location_in.shelf,
        image_url=image_url,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

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

        job.status = JobStatusEnum.REVIEW_REQUIRED.value
        job.extracted_drafts_count = len(draft_records)
        logger.info(
            "Shelf job %s completed with status REVIEW_REQUIRED and %d draft products",
            job.id,
            len(draft_records),
        )
    except Exception as exc:
        job.status = JobStatusEnum.FAILED.value
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

    db.commit()
    db.refresh(job)
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
