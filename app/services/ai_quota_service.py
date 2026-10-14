import datetime
import logging
import math
import uuid
from typing import Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.exceptions import AIQuotaExceededException
from app.db.session import SessionLocal
from app.models.scan_job import ScanJob, ScanJobStatus
from app.models.store import Store
from app.schemas.ai_quota_schema import AIQuotaResponseSchema
from app.schemas.token import TokenPayload

logger = logging.getLogger("daweros_api.ai_quota")


def get_utc_now() -> datetime.datetime:
    """Returns current UTC timestamp with timezone information."""
    return datetime.datetime.now(datetime.timezone.utc)


def check_and_apply_rolling_reset(store: Store, current_time: datetime.datetime) -> bool:
    """Evaluates whether the rolling 30-day quota period has expired for a locked store.

    If expired, resets `ai_scans_used` to 0 and anchors `ai_scans_reset_at` to current_time + 30 days.
    Returns True if a reset occurred, False otherwise.
    """
    if store.ai_scans_reset_at is None or current_time >= store.ai_scans_reset_at:
        logger.info(
            "Store %s quota period expired (was: %s, now: %s). Resetting used scans to 0.",
            store.id,
            store.ai_scans_reset_at,
            current_time,
        )
        store.ai_scans_used = 0
        store.ai_scans_reset_at = current_time + datetime.timedelta(days=30)
        return True
    return False


def get_effective_quota(db: Session, store_id: str) -> AIQuotaResponseSchema:
    """Retrieves effective quota status, applying rolling reset lazily if expired."""
    store = (
        db.query(Store)
        .filter(Store.id == store_id)
        .with_for_update()
        .first()
    )
    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store '{store_id}' not found",
        )

    now = get_utc_now()
    reset_applied = check_and_apply_rolling_reset(store, now)
    if reset_applied:
        db.commit()
        db.refresh(store)

    scans_used = store.ai_scans_used or 0
    scans_limit = store.ai_scans_limit or 30
    scans_remaining = max(0, scans_limit - scans_used)

    return AIQuotaResponseSchema(
        store_id=str(store.id),
        scans_used=scans_used,
        scans_limit=scans_limit,
        scans_remaining=scans_remaining,
        resets_at=store.ai_scans_reset_at,
    )


def reserve_scan_quota(
    db: Session,
    store_id: str,
    idempotency_key: Optional[str] = None,
) -> Tuple[ScanJob, bool]:
    """Atomically verifies quota, applies rolling reset if needed, reserves exactly 1 scan, and creates a PENDING ScanJob.

    Lock acquisition order: Store row locked first via SELECT ... FOR UPDATE.

    Guarantees:
    - Serializes concurrent reservations on the same store.
    - Idempotency: If idempotency_key matches an existing job in this store, returns that job without extra reservation.
    - Never allows ai_scans_used to exceed ai_scans_limit.
    - Captures `quota_period_reset_at` so subsequent refunds cannot corrupt new quota periods.

    Returns:
        (job: ScanJob, is_idempotent_replay: bool)

    Raises:
        HTTPException(404) if store does not exist.
        HTTPException(400) if store is inactive or not approved.
        AIQuotaExceededException(403) if quota is exhausted.
    """
    now = get_utc_now()

    # 1. Acquire row lock on Store
    store = (
        db.query(Store)
        .filter(Store.id == store_id)
        .with_for_update()
        .first()
    )
    if not store:
        logger.warning("Quota reservation rejected: store %s not found", store_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store '{store_id}' not found",
        )

    # 2. Verify store is active and approved
    if not store.is_active or (store.status and store.status.upper() != "APPROVED"):
        logger.warning(
            "Quota reservation rejected: store %s status is %s, is_active=%s",
            store_id,
            store.status,
            store.is_active,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Store is inactive or pending approval",
        )

    # 3. Idempotency check: if an idempotency key was supplied, check for existing job
    if idempotency_key and idempotency_key.strip():
        existing_job = (
            db.query(ScanJob)
            .filter(
                ScanJob.store_id == store.id,
                ScanJob.idempotency_key == idempotency_key.strip(),
            )
            .first()
        )
        if existing_job:
            logger.info(
                "Idempotent reservation match for store %s and key %s -> Returning existing job %s (status=%s)",
                store_id,
                idempotency_key,
                existing_job.id,
                existing_job.status,
            )
            return existing_job, True

    # 4. Check and apply rolling 30-day reset
    check_and_apply_rolling_reset(store, now)

    # 5. Check quota limits
    limit = store.ai_scans_limit or 30
    used = store.ai_scans_used or 0

    if used >= limit:
        remaining_seconds = max(0.0, (store.ai_scans_reset_at - now).total_seconds())
        resets_in_days = max(0, math.ceil(remaining_seconds / 86400))
        logger.warning(
            "Quota exceeded for store %s: used=%d, limit=%d, resets_in_days=%d",
            store_id,
            used,
            limit,
            resets_in_days,
        )
        raise AIQuotaExceededException(
            message="The store has reached its AI scan quota.",
            scans_used=used,
            scans_limit=limit,
            resets_in_days=resets_in_days,
            alternative="EXCEL_BULK_IMPORT",
        )

    # 6. Reserve exactly 1 scan
    store.ai_scans_used = used + 1

    # 7. Create persistent audit record
    job = ScanJob(
        id=str(uuid.uuid4()),
        store_id=store.id,
        status=ScanJobStatus.PENDING.value,
        quota_period_reset_at=store.ai_scans_reset_at,
        idempotency_key=idempotency_key.strip() if idempotency_key else None,
    )
    db.add(job)

    # 8. Commit atomic transaction
    db.commit()
    db.refresh(job)

    logger.info(
        "Successfully reserved AI scan quota for store %s. Job ID: %s, Quota used: %d/%d",
        store_id,
        job.id,
        store.ai_scans_used,
        store.ai_scans_limit,
    )
    return job, False


def refund_scan_quota(
    job_id: str,
    store_id: str,
    failure_reason: str,
    error_details: Optional[str] = None,
    db: Optional[Session] = None,
) -> bool:
    """Atomically and idempotently transitions a failed/stale job to REFUNDED and restores 1 scan.

    Guarantees:
    1. Lock order: Always locks Store first, then checks Job, matching reservation order to avoid deadlocks.
    2. Only permits refunds for jobs in eligible non-completed states (PENDING, PROCESSING, FAILED).
    3. Conditional state transition: updates job to REFUNDED only if current status is NOT REFUNDED and NOT COMPLETED.
    4. Quota decrement occurs if and only if the refund transition successfully claims the job.
    5. Old-period protection: If the store quota period has reset since the scan was created,
       the job is marked REFUNDED, but new-period quota is NOT decremented.
    6. Decrement is strictly non-negative: `ai_scans_used = max(0, ai_scans_used - 1)`.
    7. Fully idempotent: repeated calls return False and do not double-decrement.
    """
    owns_session = False
    if db is None:
        db = SessionLocal()
        owns_session = True

    try:
        now = get_utc_now()

        # Step 1: Acquire lock on Store first (consistent lock hierarchy)
        store = (
            db.query(Store)
            .filter(Store.id == store_id)
            .with_for_update()
            .first()
        )
        if not store:
            logger.warning("Refund aborted: store %s not found", store_id)
            db.rollback()
            return False

        # Step 2: Acquire lock on Job
        job = (
            db.query(ScanJob)
            .filter(
                ScanJob.id == job_id,
                ScanJob.store_id == store_id,
            )
            .with_for_update()
            .first()
        )
        if not job:
            logger.warning("Refund aborted: job %s not found for store %s", job_id, store_id)
            db.rollback()
            return False

        # Step 3: Check eligibility: COMPLETED or already REFUNDED jobs can NEVER be refunded
        if job.status == ScanJobStatus.COMPLETED.value:
            logger.warning("Refund rejected: job %s is already COMPLETED", job_id)
            db.rollback()
            return False

        if job.status == ScanJobStatus.REFUNDED.value:
            logger.info("Refund already claimed for job %s. Idempotently ignoring.", job_id)
            db.rollback()
            return False

        # Step 4: Atomic conditional update on ScanJob
        rows_affected = (
            db.query(ScanJob)
            .filter(
                ScanJob.id == job_id,
                ScanJob.store_id == store_id,
                ScanJob.status.notin_([ScanJobStatus.REFUNDED.value, ScanJobStatus.COMPLETED.value]),
            )
            .update(
                {
                    ScanJob.status: ScanJobStatus.REFUNDED.value,
                    ScanJob.refunded_at: now,
                    ScanJob.failure_reason: failure_reason[:255] if failure_reason else "GENERIC_FAILURE",
                    ScanJob.error_details: error_details[:2000] if error_details else None,
                    ScanJob.updated_at: now,
                },
                synchronize_session=False,
            )
        )

        if rows_affected == 0:
            logger.warning("Refund conditional update claimed 0 rows for job %s. No quota adjusted.", job_id)
            db.rollback()
            return False

        # Step 5: Quota adjustment with old-period boundary protection
        # If the store's current period reset timestamp differs from the job's period,
        # the store has already rolled over into a new period! Do not touch new-period counter.
        is_same_quota_period = (
            job.quota_period_reset_at is not None
            and store.ai_scans_reset_at is not None
            and abs((job.quota_period_reset_at - store.ai_scans_reset_at).total_seconds()) < 1.0
        )

        if is_same_quota_period:
            store.ai_scans_used = max(0, (store.ai_scans_used or 0) - 1)
            logger.info(
                "Refund successful: restored 1 scan for store %s (new used: %d). Job %s marked REFUNDED.",
                store_id,
                store.ai_scans_used,
                job_id,
            )
        else:
            logger.info(
                "Refund processed for historical period (job period: %s, store period: %s). "
                "Job %s marked REFUNDED without decrementing current period quota.",
                job.quota_period_reset_at,
                store.ai_scans_reset_at,
                job_id,
            )

        db.commit()
        return True

    except Exception as exc:
        db.rollback()
        logger.error("Error during refund transaction for job %s: %s", job_id, exc, exc_info=True)
        return False
    finally:
        if owns_session:
            db.close()


def claim_job_for_processing(
    job_id: str,
    store_id: str,
    worker_id: str,
    db: Session,
) -> bool:
    """Atomically claims a PENDING job for processing and establishes a worker lease.

    Guarantees:
    - Only a PENDING job can transition to PROCESSING.
    - Sets initial heartbeat and lease_owner.
    """
    now = get_utc_now()
    rows = (
        db.query(ScanJob)
        .filter(
            ScanJob.id == job_id,
            ScanJob.store_id == store_id,
            ScanJob.status == ScanJobStatus.PENDING.value,
        )
        .update(
            {
                ScanJob.status: ScanJobStatus.PROCESSING.value,
                ScanJob.started_at: now,
                ScanJob.heartbeat_at: now,
                ScanJob.lease_owner: worker_id,
                ScanJob.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    if rows > 0:
        db.commit()
        logger.info("Worker %s successfully claimed job %s for processing", worker_id, job_id)
        return True
    logger.warning("Worker %s failed to claim job %s (already claimed or cancelled)", worker_id, job_id)
    return False


def update_job_heartbeat(
    job_id: str,
    worker_id: str,
    db: Session,
) -> bool:
    """Updates heartbeat for a currently owned processing job."""
    now = get_utc_now()
    rows = (
        db.query(ScanJob)
        .filter(
            ScanJob.id == job_id,
            ScanJob.status == ScanJobStatus.PROCESSING.value,
            ScanJob.lease_owner == worker_id,
        )
        .update(
            {
                ScanJob.heartbeat_at: now,
                ScanJob.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    if rows > 0:
        db.commit()
        return True
    return False


def complete_job_processing(
    job_id: str,
    store_id: str,
    worker_id: str,
    shelf_job_id: Optional[str],
    extracted_drafts_count: int,
    db: Session,
) -> bool:
    """Atomically marks a PROCESSING job as COMPLETED.

    Guarantees:
    - Worker lease must match.
    - Reconciler-cancelled, refunded, or failed jobs CANNOT transition to COMPLETED.
    """
    now = get_utc_now()
    rows = (
        db.query(ScanJob)
        .filter(
            ScanJob.id == job_id,
            ScanJob.store_id == store_id,
            ScanJob.status == ScanJobStatus.PROCESSING.value,
            ScanJob.lease_owner == worker_id,
        )
        .update(
            {
                ScanJob.status: ScanJobStatus.COMPLETED.value,
                ScanJob.completed_at: now,
                ScanJob.shelf_job_id: shelf_job_id,
                ScanJob.extracted_drafts_count: extracted_drafts_count,
                ScanJob.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    if rows > 0:
        db.commit()
        logger.info("Worker %s successfully completed job %s (%d drafts)", worker_id, job_id, extracted_drafts_count)
        return True
    logger.warning(
        "Worker %s could not complete job %s (lease expired, or job claimed by reconciler)",
        worker_id,
        job_id,
    )
    return False


def reconcile_stale_jobs(
    max_age_seconds: int = 900,
    db: Optional[Session] = None,
) -> int:
    """Crash recovery and stale job detection service.

    Finds jobs stuck in PENDING or PROCESSING whose lease/heartbeat has expired (> 15 minutes).
    Atomically claims them for recovery and triggers the refund engine.

    Returns:
        Number of stale jobs successfully recovered and refunded.
    """
    owns_session = False
    if db is None:
        db = SessionLocal()
        owns_session = True

    recovered_count = 0
    try:
        now = get_utc_now()
        stale_threshold = now - datetime.timedelta(seconds=max_age_seconds)

        # 1. Identify stale candidate jobs using indexed columns
        stale_jobs = (
            db.query(ScanJob)
            .filter(
                ScanJob.status.in_([ScanJobStatus.PENDING.value, ScanJobStatus.PROCESSING.value]),
                func.coalesce(ScanJob.heartbeat_at, ScanJob.started_at, ScanJob.created_at) < stale_threshold,
            )
            .all()
        )

        for job in stale_jobs:
            logger.warning(
                "Stale job detected: ID=%s, store=%s, status=%s, last_active=%s. Attempting recovery.",
                job.id,
                job.store_id,
                job.status,
                job.heartbeat_at or job.started_at or job.created_at,
            )

            # Atomically claim the transition to FAILED
            claimed_rows = (
                db.query(ScanJob)
                .filter(
                    ScanJob.id == job.id,
                    ScanJob.status.in_([ScanJobStatus.PENDING.value, ScanJobStatus.PROCESSING.value]),
                )
                .update(
                    {
                        ScanJob.status: ScanJobStatus.FAILED.value,
                        ScanJob.failure_reason: "STALE_JOB_LEASE_EXPIRED",
                        ScanJob.error_details: f"Worker lease expired after {max_age_seconds}s without heartbeat",
                        ScanJob.updated_at: now,
                    },
                    synchronize_session=False,
                )
            )

            if claimed_rows > 0:
                db.commit()
                # Step 2: Trigger idempotent refund
                refund_success = refund_scan_quota(
                    job_id=str(job.id),
                    store_id=str(job.store_id),
                    failure_reason="STALE_JOB_LEASE_EXPIRED",
                    error_details="Refund issued by automated crash recovery reconciliation",
                )
                if refund_success:
                    recovered_count += 1
                    logger.info("Successfully recovered and refunded stale job %s", job.id)

        return recovered_count
    except Exception as exc:
        db.rollback()
        logger.error("Error during stale job reconciliation: %s", exc, exc_info=True)
        return recovered_count
    finally:
        if owns_session:
            db.close()
