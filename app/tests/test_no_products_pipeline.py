import datetime
import io
import json
import uuid
from unittest.mock import MagicMock, patch
import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.audit_log import AuditLog
from app.models.scan_job import ScanJob, ScanJobStatus
from app.models.shelf_job import DraftProduct, ShelfJob
from app.models.store import Store
from app.models.user import User
from app.schemas.shelf_job_schema import GeminiExtractionResult, ShelfJobCreateSchema
from app.services.shelf_extraction_worker import process_gemini_vision_bg

client = TestClient(app)


def create_token(user_id: str, role: str = "User", store_id: str | None = None) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "exp": int((now + datetime.timedelta(hours=1)).timestamp()),
        "iat": int(now.timestamp()),
    }
    if store_id:
        payload["store_id"] = str(store_id)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@pytest.fixture
def store():
    db = SessionLocal()
    try:
        s = db.query(Store).first()
        if not s:
            u = db.query(User).first()
            if not u:
                u = User(
                    id=str(uuid.uuid4()),
                    email="pipeline_test_owner@dawer.com",
                    full_name="Pipeline Test Owner",
                    role="User",
                )
                db.add(u)
                db.commit()
                db.refresh(u)
            s = Store(
                id=str(uuid.uuid4()),
                name="Pipeline Test Store",
                owner_id=str(u.id),
                status="APPROVED",
                verification_status="APPROVED",
                is_active=True,
            )
            db.add(s)
            db.commit()
            db.refresh(s)
        return s
    finally:
        db.close()


def test_background_worker_no_products_detected_review_required(store):
    """Verifies that when Gemini Vision detects 0 products:
    1. process_gemini_vision_bg does NOT fail or crash the task.
    2. Draft record (ShelfJob) is saved with status = 'REVIEW_REQUIRED' (BR-17) and products_count = 0.
    3. Attached warning in metadata has warning = 'NO_PRODUCTS_FOUND' and localized user_message.
    4. An AuditLog entry is recorded for BR-17 human-in-the-loop review.
    5. The ScanJob is completed without failure or refund.
    6. Product Draft API (GET /api/v1/stores/{store_id}/product-drafts/{job_id}) returns hasWarning: true, productsCount: 0.
    """
    db = SessionLocal()
    scan_job_id = str(uuid.uuid4())
    try:
        # Create a PENDING scan job
        scan_job = ScanJob(
            id=scan_job_id,
            store_id=store.id,
            status=ScanJobStatus.PENDING.value,
            quota_period_reset_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30),
            extracted_drafts_count=0,
        )
        db.add(scan_job)
        db.commit()
    finally:
        db.close()

    mock_empty_result = GeminiExtractionResult(
        status="NO_PRODUCTS_DETECTED",
        products=[],
        message="لم يتم العثور على أي منتجات تجارية في الصورة",
        has_warning=True,
        warning_code="NO_PRODUCTS_FOUND",
    )

    dummy_image = b"\xff\xd8\xffdummy_out_of_domain_drawing_JOB_0898"
    loc = ShelfJobCreateSchema(zone="A", aisle="2", rack="R1", shelf="S1")

    with patch("app.services.gemini_service.analyze_shelf_image", return_value=mock_empty_result):
        process_gemini_vision_bg(
            job_id=scan_job_id,
            store_id=str(store.id),
            image_bytes=dummy_image,
            location_in=loc,
            filename="JOB-0898.jpg",
        )

    # Inspect DB state
    db = SessionLocal()
    try:
        updated_scan = db.query(ScanJob).filter(ScanJob.id == scan_job_id).first()
        assert updated_scan is not None
        assert updated_scan.status == ScanJobStatus.COMPLETED.value
        assert updated_scan.shelf_job_id is not None
        assert updated_scan.extracted_drafts_count == 0

        shelf_job = db.query(ShelfJob).filter(ShelfJob.id == updated_scan.shelf_job_id).first()
        assert shelf_job is not None
        # Requirement 2: status = 'REVIEW_REQUIRED' (BR-17) and products_count = 0
        assert shelf_job.status == "REVIEW_REQUIRED"
        assert shelf_job.extracted_drafts_count == 0
        assert shelf_job.error_message is not None

        # Verify warning metadata inside error_message
        meta = json.loads(shelf_job.error_message)
        assert meta["warning"] == "NO_PRODUCTS_FOUND"
        assert meta["user_message"] == "لم يتعرف النظام على أي منتجات تجارية في هذه الصورة. يرجى التأكد من توجيه الكاميرا لرف حقيقي ومضاء جيداً."

        # Verify BR-17 audit log was written
        audit = (
            db.query(AuditLog)
            .filter(
                AuditLog.entity_id == str(shelf_job.id),
                AuditLog.action == "SHELF_SCAN_REVIEW_REQUIRED",
            )
            .first()
        )
        assert audit is not None
        assert audit.store_id == str(store.id)
        assert "NO_PRODUCTS_FOUND" in audit.new_value

        # Verify child draft products table has 0 items
        drafts = db.query(DraftProduct).filter(DraftProduct.shelf_job_id == shelf_job.id).all()
        assert len(drafts) == 0
    finally:
        db.close()

    # Requirement 3: GET /api/v1/stores/{store_id}/product-drafts/{job_id} using scan_job_id
    token = create_token(user_id=store.owner_id, store_id=store.id)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get(
        f"/api/v1/stores/{store.id}/product-drafts/{scan_job_id}",
        headers=headers,
    )
    assert resp.status_code == 200
    res_data = resp.json()

    assert res_data["productsCount"] == 0
    assert res_data["hasWarning"] is True
    assert res_data["warningCode"] == "NO_PRODUCTS_FOUND"
    assert res_data["userMessage"] == "لم يتعرف النظام على أي منتجات تجارية في هذه الصورة. يرجى التأكد من توجيه الكاميرا لرف حقيقي ومضاء جيداً."
    assert res_data["status"] == "REVIEW_REQUIRED"
    assert res_data["products"] == []


def test_create_shelf_job_sync_no_products_returns_review_required(store):
    """Verifies that synchronous shelf capture job creation with 0 products also sets status REVIEW_REQUIRED."""
    token = create_token(user_id=store.owner_id, store_id=store.id)
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("non_shelf.jpg", io.BytesIO(b"\xff\xd8\xffdummy_cat_photo"), "image/jpeg")}
    data = {"zone": "B", "aisle": "3"}

    mock_empty_result = GeminiExtractionResult(
        status="NO_PRODUCTS_DETECTED",
        products=[],
        message="لم يتم العثور على أي منتجات تجارية",
        has_warning=True,
        warning_code="NO_PRODUCTS_FOUND",
    )

    with patch("app.services.gemini_service.analyze_shelf_image", return_value=mock_empty_result):
        response = client.post(
            f"/api/v1/stores/{store.id}/shelf-jobs",
            headers=headers,
            files=files,
            data=data,
        )

    assert response.status_code == 201
    job_data = response.json()
    assert job_data["status"] == "REVIEW_REQUIRED"
    assert job_data["extracted_drafts_count"] == 0
    assert job_data["hasWarning"] is True
    assert job_data["warningCode"] == "NO_PRODUCTS_FOUND"
    assert job_data["userMessage"] == "لم يتعرف النظام على أي منتجات تجارية في هذه الصورة. يرجى التأكد من توجيه الكاميرا لرف حقيقي ومضاء جيداً."
