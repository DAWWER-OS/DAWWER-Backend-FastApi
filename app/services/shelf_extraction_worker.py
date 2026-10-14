import json
import logging
import sys
import traceback
import uuid
from typing import Optional

from app.db.session import SessionLocal
from app.models.audit_log import AuditLog
from app.models.shelf_job import DraftProduct, ShelfJob
from app.schemas.shelf_job_schema import ShelfJobCreateSchema
from app.services import gemini_service
from app.services.ai_quota_service import (
    claim_job_for_processing,
    complete_job_processing,
    refund_scan_quota,
)
from app.services.storage_service import save_shelf_image

logger = logging.getLogger("daweros_api.extraction_worker")


def sanitize_error(exc: Exception) -> tuple[str, str]:
    """Sanitizes exception into machine-readable category and clean message without secrets or stack traces."""
    msg = str(exc)
    exc_type = type(exc).__name__

    if "API_KEY" in msg or "api key" in msg.lower():
        return "PROVIDER_AUTH_ERROR", "AI provider authentication failed. Check server configuration."
    if "quota" in msg.lower() or "resource has been exhausted" in msg.lower() or "429" in msg:
        return "PROVIDER_RATE_LIMIT", "AI provider rate limit or quota exceeded. Please retry later."
    if "timeout" in msg.lower() or "timed out" in msg.lower():
        return "PROVIDER_TIMEOUT", "AI service request timed out."
    if "JSONDecodeError" in exc_type or "parse" in msg.lower():
        return "PROVIDER_UNPARSEABLE_RESPONSE", "Failed to parse retail product extraction response."
    if "ConnectionError" in exc_type or "network" in msg.lower():
        return "PROVIDER_NETWORK_ERROR", "Network failure connecting to AI provider."

    return "EXTRACTION_FAILED", f"Extraction processing error: {msg[:200]}"


def process_gemini_vision_bg(
    job_id: str,
    store_id: str,
    image_bytes: bytes,
    location_in: Optional[ShelfJobCreateSchema] = None,
    filename: Optional[str] = None,
) -> None:
    """Background worker task executed via FastAPI BackgroundTasks for Gemini Vision shelf extraction.

    Guarantees:
    1. Uses a fresh, dedicated database session.
    2. Atomically claims the job with a unique worker lease ID.
    3. Executes Gemini Vision extraction.
    4. When 0 products detected or status is NO_PRODUCTS_DETECTED:
       - Does NOT fail or crash.
       - Saves draft record with status='REVIEW_REQUIRED' (BR-17) and products_count=0.
       - Stores localized warning metadata: NO_PRODUCTS_FOUND.
       - Records BR-17 human-in-the-loop audit log.
    5. When products are found: persists ShelfJob and DraftProduct records.
    6. Marks ScanJob COMPLETED upon processing completion.
    7. On qualifying external failure, marks ScanJob FAILED and triggers atomic refund.
    8. Database session is guaranteed to close cleanly.
    """
    worker_id = f"worker-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        logger.info(
            "Worker %s starting async extraction for scan job %s (store %s, %d image bytes)",
            worker_id,
            job_id,
            store_id,
            len(image_bytes),
        )

        # 1. Atomically claim job
        claimed = claim_job_for_processing(job_id=job_id, store_id=store_id, worker_id=worker_id, db=db)
        if not claimed:
            logger.warning("Worker %s aborted: job %s was not in PENDING state", worker_id, job_id)
            return

        # 2. Save image to disk if storage is configured
        image_url: Optional[str] = None
        if image_bytes:
            try:
                _, image_url = save_shelf_image(
                    store_id=store_id,
                    raw_filename=filename or f"scan_{job_id}.jpg",
                    image_bytes=image_bytes,
                )
            except Exception as save_exc:
                logger.warning("Could not persist image to disk for store %s: %s", store_id, save_exc)

        # 3. Call Gemini Vision AI extraction
        try:
            extracted_items = gemini_service.analyze_shelf_image(image_bytes)
        except Exception as ai_exc:
            reason_code, sanitized_msg = sanitize_error(ai_exc)
            logger.error(
                "Gemini analysis failure for job %s: reason=%s msg=%s\n%s",
                job_id,
                reason_code,
                sanitized_msg,
                traceback.format_exc(),
            )
            # Trigger atomic refund on real unhandled AI provider failure
            refund_scan_quota(
                job_id=job_id,
                store_id=store_id,
                failure_reason=reason_code,
                error_details=sanitized_msg,
                db=db,
            )
            return

        # 4. Handle extraction results under BR-17
        products = getattr(extracted_items, "products", extracted_items)
        extraction_status = getattr(
            extracted_items,
            "status",
            "SUCCESS" if len(products) > 0 else "NO_PRODUCTS_DETECTED",
        )
        is_no_products = (len(products) == 0) or (extraction_status == "NO_PRODUCTS_DETECTED")

        shelf_job_record_id: Optional[str] = None
        draft_count = 0
        try:
            if is_no_products:
                warning_data = {
                    "warning": "NO_PRODUCTS_FOUND",
                    "warning_code": "NO_PRODUCTS_FOUND",
                    "user_message": "لم يتعرف النظام على أي منتجات تجارية في هذه الصورة. يرجى التأكد من توجيه الكاميرا لرف حقيقي ومضاء جيداً.",
                    "has_warning": True,
                    "products_count": 0,
                    "status": "REVIEW_REQUIRED",
                }
                shelf_record = ShelfJob(
                    store_id=store_id,
                    status="REVIEW_REQUIRED",
                    zone=location_in.zone if location_in else "A",
                    aisle=location_in.aisle if location_in else "1",
                    rack=location_in.rack if location_in else None,
                    shelf=location_in.shelf if location_in else None,
                    image_url=image_url,
                    extracted_drafts_count=0,
                    error_message=json.dumps(warning_data, ensure_ascii=False),
                )
                db.add(shelf_record)
                db.flush()

                # BR-17 Human-in-the-loop audit log
                audit_record = AuditLog(
                    store_id=store_id,
                    action="SHELF_SCAN_REVIEW_REQUIRED",
                    entity_type="shelf_job",
                    entity_id=str(shelf_record.id),
                    new_value=json.dumps(warning_data, ensure_ascii=False),
                )
                db.add(audit_record)
                db.commit()
                db.refresh(shelf_record)
                shelf_job_record_id = shelf_record.id
                draft_count = 0
                logger.warning(
                    "Worker %s: 0 products detected for job %s (store %s). Saved with status REVIEW_REQUIRED under BR-17.",
                    worker_id,
                    job_id,
                    store_id,
                )
            else:
                shelf_record = ShelfJob(
                    store_id=store_id,
                    status="COMPLETED",
                    zone=location_in.zone if location_in else "A",
                    aisle=location_in.aisle if location_in else "1",
                    rack=location_in.rack if location_in else None,
                    shelf=location_in.shelf if location_in else None,
                    image_url=image_url,
                    extracted_drafts_count=len(products),
                )
                db.add(shelf_record)
                db.commit()
                db.refresh(shelf_record)
                shelf_job_record_id = shelf_record.id

                draft_records = []
                for item in products:
                    draft = DraftProduct(
                        store_id=store_id,
                        shelf_job_id=shelf_record.id,
                        proposed_name=item.proposed_name,
                        estimated_price=item.estimated_price or 0.0,
                        category_hint=item.category_hint,
                        pack_size=item.pack_size,
                        barcode_detected=item.barcode_detected,
                        confidence_score=item.confidence_score or 0.0,
                        zone=location_in.zone if location_in else "A",
                        aisle=location_in.aisle if location_in else "1",
                        rack=location_in.rack if location_in else None,
                        shelf=location_in.shelf if location_in else None,
                        status="PENDING_REVIEW",
                    )
                    draft_records.append(draft)

                if draft_records:
                    db.add_all(draft_records)
                    db.commit()
                draft_count = len(draft_records)

        except Exception as db_exc:
            logger.error("Failed to commit shelf drafts for job %s: %s", job_id, db_exc, exc_info=True)
            db.rollback()
            refund_scan_quota(
                job_id=job_id,
                store_id=store_id,
                failure_reason="DATABASE_PERSISTENCE_ERROR",
                error_details="Failed to persist extracted draft products to database",
                db=db,
            )
            return

        # 5. Atomically complete the scan job
        completed = complete_job_processing(
            job_id=job_id,
            store_id=store_id,
            worker_id=worker_id,
            shelf_job_id=shelf_job_record_id,
            extracted_drafts_count=draft_count,
            db=db,
        )
        if not completed:
            logger.warning(
                "Job %s could not be marked COMPLETED by worker %s (may have been claimed by recovery)",
                job_id,
                worker_id,
            )

    except Exception as unhandled_exc:
        logger.critical(
            "Unhandled exception in extraction worker for job %s: %s\n%s",
            job_id,
            unhandled_exc,
            traceback.format_exc(),
        )
        try:
            refund_scan_quota(
                job_id=job_id,
                store_id=store_id,
                failure_reason="UNHANDLED_WORKER_EXCEPTION",
                error_details="An unexpected worker error occurred",
                db=db,
            )
        except Exception:
            pass
    finally:
        db.close()


# Backward compatibility alias
process_shelf_extraction_async = process_gemini_vision_bg
