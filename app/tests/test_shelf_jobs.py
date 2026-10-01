import datetime
import io
import uuid
from unittest.mock import patch
import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.shelf_job import DraftProduct, ShelfJob
from app.models.store import Store
from app.models.user import User
from app.schemas.shelf_job_schema import ExtractedDraftProductSchema

client = TestClient(app)

MOCK_EXTRACTED_PRODUCTS = [
    ExtractedDraftProductSchema(
        proposed_name="عصير ربيع 1 لتر",
        estimated_price=3.5,
        category_hint="مشروبات",
        pack_size="1L",
        barcode_detected="123456789",
        confidence_score=0.92,
    )
]


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
                    email="test_owner@dawer.com",
                    full_name="Test Owner",
                    role="User",
                )
                db.add(u)
                db.commit()
                db.refresh(u)
            s = Store(
                id=str(uuid.uuid4()),
                name="Test Store",
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


@pytest.fixture(autouse=True)
def cleanup():
    yield
    db = SessionLocal()
    try:
        db.query(DraftProduct).delete()
        db.query(ShelfJob).delete()
        db.commit()
    finally:
        db.close()


def test_create_shelf_job_success(store):
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("shelf.jpg", io.BytesIO(b"\xff\xd8\xffdummyjpeg"), "image/jpeg")}
    data = {"zone": "A", "aisle": "1"}

    with patch("app.services.gemini_service.analyze_shelf_image", return_value=MOCK_EXTRACTED_PRODUCTS):
        response = client.post(
            f"/api/v1/stores/{store.id}/shelf-jobs",
            headers=headers,
            files=files,
            data=data,
        )

    assert response.status_code == 201
    res_data = response.json()
    assert res_data["status"] in ["COMPLETED", "REVIEW_REQUIRED"]
    assert res_data["extracted_drafts_count"] == 1
    assert res_data["zone"] == "A"
    assert res_data["aisle"] == "1"


def test_create_shelf_job_invalid_file_fails(store):
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("shelf.txt", io.BytesIO(b"not an image"), "text/plain")}
    data = {"zone": "A", "aisle": "1"}

    response = client.post(
        f"/api/v1/stores/{store.id}/shelf-jobs",
        headers=headers,
        files=files,
        data=data,
    )

    assert response.status_code == 400


def test_get_shelf_job_details(store):
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("shelf.jpg", io.BytesIO(b"\xff\xd8\xffdummyjpeg"), "image/jpeg")}
    data = {"zone": "Zone X", "aisle": "Aisle Y", "rack": "R1", "shelf": "S2"}

    with patch("app.services.gemini_service.analyze_shelf_image", return_value=MOCK_EXTRACTED_PRODUCTS):
        create_resp = client.post(
            f"/api/v1/stores/{store.id}/shelf-jobs",
            headers=headers,
            files=files,
            data=data,
        )
    assert create_resp.status_code == 201
    job_id = create_resp.json()["id"]

    get_resp = client.get(
        f"/api/v1/stores/{store.id}/shelf-jobs/{job_id}",
        headers=headers,
    )
    assert get_resp.status_code == 200
    res_data = get_resp.json()
    assert res_data["id"] == job_id
    assert res_data["zone"] == "Zone X"
    assert res_data["aisle"] == "Aisle Y"
    assert res_data["rack"] == "R1"
    assert res_data["shelf"] == "S2"


def test_list_store_shelf_jobs(store):
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("shelf.jpg", io.BytesIO(b"\xff\xd8\xffdummyjpeg"), "image/jpeg")}
    data = {"zone": "A", "aisle": "1"}

    with patch("app.services.gemini_service.analyze_shelf_image", return_value=MOCK_EXTRACTED_PRODUCTS):
        client.post(
            f"/api/v1/stores/{store.id}/shelf-jobs",
            headers=headers,
            files=files,
            data=data,
        )

    list_resp = client.get(
        f"/api/v1/stores/{store.id}/shelf-jobs",
        headers=headers,
    )
    assert list_resp.status_code == 200
    jobs = list_resp.json()
    assert isinstance(jobs, list)
    assert len(jobs) >= 1


def test_store_isolation_br14_forbidden(store):
    other_token = create_token(
        user_id="other_user_123", role="User", store_id="other_store_456"
    )
    other_headers = {"Authorization": f"Bearer {other_token}"}
    files = {"file": ("shelf.jpg", io.BytesIO(b"\xff\xd8\xffdummyjpeg"), "image/jpeg")}
    data = {"zone": "A", "aisle": "1"}

    create_resp = client.post(
        f"/api/v1/stores/{store.id}/shelf-jobs",
        headers=other_headers,
        files=files,
        data=data,
    )
    assert create_resp.status_code == 403

    get_resp = client.get(
        f"/api/v1/stores/{store.id}/shelf-jobs/any-job-id",
        headers=other_headers,
    )
    assert get_resp.status_code == 403

    list_resp = client.get(
        f"/api/v1/stores/{store.id}/shelf-jobs",
        headers=other_headers,
    )
    assert list_resp.status_code == 403


def test_create_shelf_job_arabic_filename_and_image_url(store):
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}
    arabic_filename = "صورة_الرف_1.jpg"
    image_bytes = b"\xff\xd8\xffdummy_arabic_jpeg_content"
    files = {"file": (arabic_filename, io.BytesIO(image_bytes), "image/jpeg")}
    data = {"zone": "المنطقة أ", "aisle": "ممر 1"}

    with patch("app.services.gemini_service.analyze_shelf_image", return_value=MOCK_EXTRACTED_PRODUCTS):
        response = client.post(
            f"/api/v1/stores/{store.id}/shelf-jobs",
            headers=headers,
            files=files,
            data=data,
        )

    assert response.status_code == 201
    res_data = response.json()
    assert res_data["status"] in ["COMPLETED", "REVIEW_REQUIRED"]
    assert res_data["extracted_drafts_count"] == 1
    assert res_data["image_url"] is not None
    assert f"/uploads/shelf_jobs/{store.id}/" in res_data["image_url"]

    # Verify that the image can be fetched via the static route
    img_resp = client.get(res_data["image_url"])
    assert img_resp.status_code == 200
    assert img_resp.content == image_bytes


def test_create_shelf_job_ai_failure_sets_failed_status(store):
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("shelf_err.jpg", io.BytesIO(b"\xff\xd8\xffdummyjpeg"), "image/jpeg")}
    data = {"zone": "Z", "aisle": "1"}

    with patch("app.services.gemini_service.analyze_shelf_image", side_effect=ValueError("Simulated Gemini API timeout")):
        response = client.post(
            f"/api/v1/stores/{store.id}/shelf-jobs",
            headers=headers,
            files=files,
            data=data,
        )

    assert response.status_code == 201
    res_data = response.json()
    assert res_data["status"] == "FAILED"
    assert res_data["extracted_drafts_count"] == 0
    assert res_data["image_url"] is not None


def test_delete_shelf_job_success(store):
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("shelf_to_del.jpg", io.BytesIO(b"\xff\xd8\xffimage_to_delete"), "image/jpeg")}
    data = {"zone": "DelZone", "aisle": "DelAisle"}

    with patch("app.services.gemini_service.analyze_shelf_image", return_value=MOCK_EXTRACTED_PRODUCTS):
        create_resp = client.post(
            f"/api/v1/stores/{store.id}/shelf-jobs",
            headers=headers,
            files=files,
            data=data,
        )
    assert create_resp.status_code == 201
    job_id = create_resp.json()["id"]
    image_url = create_resp.json()["image_url"]

    # Verify image exists on disk
    assert image_url is not None
    import urllib.parse
    from pathlib import Path
    image_file_path = Path("uploads") / "shelf_jobs" / str(store.id) / Path(urllib.parse.unquote(image_url)).name
    assert image_file_path.exists(), f"Image file {image_file_path} should exist before deletion"

    # Delete shelf job via main route
    del_resp = client.delete(
        f"/api/v1/stores/{store.id}/shelf-jobs/{job_id}",
        headers=headers,
    )
    assert del_resp.status_code == 200
    del_data = del_resp.json()
    assert del_data["deleted"] is True
    assert del_data["job_id"] == job_id
    assert del_data["store_id"] == str(store.id)

    # Verify image is deleted from disk
    assert not image_file_path.exists(), f"Image file {image_file_path} should be deleted from disk"

    # Verify DB record is deleted
    db = SessionLocal()
    try:
        job = db.query(ShelfJob).filter(ShelfJob.id == job_id).first()
        assert job is None
        drafts = db.query(DraftProduct).filter(DraftProduct.shelf_job_id == job_id).all()
        assert len(drafts) == 0
    finally:
        db.close()


def test_delete_shelf_job_not_found(store):
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}
    del_resp = client.delete(
        f"/api/v1/stores/{store.id}/shelf-jobs/non-existent-id",
        headers=headers,
    )
    assert del_resp.status_code == 404


def test_delete_shelf_job_br14_forbidden(store):
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("shelf_br14.jpg", io.BytesIO(b"\xff\xd8\xffimage"), "image/jpeg")}
    data = {"zone": "Z", "aisle": "1"}

    with patch("app.services.gemini_service.analyze_shelf_image", return_value=MOCK_EXTRACTED_PRODUCTS):
        create_resp = client.post(
            f"/api/v1/stores/{store.id}/shelf-jobs",
            headers=headers,
            files=files,
            data=data,
        )
    assert create_resp.status_code == 201
    job_id = create_resp.json()["id"]

    other_token = create_token(user_id="other_user_id", role="User", store_id="other_store_id")
    other_headers = {"Authorization": f"Bearer {other_token}"}

    del_resp = client.delete(
        f"/api/v1/stores/{store.id}/shelf-jobs/{job_id}",
        headers=other_headers,
    )
    assert del_resp.status_code == 403


def test_delete_shelf_job_legacy_unprefixed_store(store):
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("shelf_unprefixed.jpg", io.BytesIO(b"\xff\xd8\xffimage"), "image/jpeg")}
    data = {"zone": "Z", "aisle": "1"}

    with patch("app.services.gemini_service.analyze_shelf_image", return_value=MOCK_EXTRACTED_PRODUCTS):
        create_resp = client.post(
            f"/api/v1/stores/{store.id}/shelf-jobs",
            headers=headers,
            files=files,
            data=data,
        )
    job_id = create_resp.json()["id"]

    del_resp = client.delete(
        f"/stores/{store.id}/shelf-jobs/{job_id}",
        headers=headers,
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True


def test_delete_shelf_job_legacy_sessions_and_captures(store):
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}

    # Test /shelf/sessions/{id}
    files1 = {"file": ("shelf_sess.jpg", io.BytesIO(b"\xff\xd8\xffimage"), "image/jpeg")}
    with patch("app.services.gemini_service.analyze_shelf_image", return_value=MOCK_EXTRACTED_PRODUCTS):
        create_resp1 = client.post(
            f"/api/v1/stores/{store.id}/shelf-jobs",
            headers=headers,
            files=files1,
            data={"zone": "Z", "aisle": "1"},
        )
    job_id1 = create_resp1.json()["id"]

    del_sess_resp = client.delete(f"/shelf/sessions/{job_id1}", headers=headers)
    assert del_sess_resp.status_code == 200
    assert del_sess_resp.json()["deleted"] is True

    # Test /shelf/captures/{id}
    files2 = {"file": ("shelf_cap.jpg", io.BytesIO(b"\xff\xd8\xffimage"), "image/jpeg")}
    with patch("app.services.gemini_service.analyze_shelf_image", return_value=MOCK_EXTRACTED_PRODUCTS):
        create_resp2 = client.post(
            f"/api/v1/stores/{store.id}/shelf-jobs",
            headers=headers,
            files=files2,
            data={"zone": "Z", "aisle": "1"},
        )
    job_id2 = create_resp2.json()["id"]

    del_cap_resp = client.delete(f"/shelf/captures/{job_id2}", headers=headers)
    assert del_cap_resp.status_code == 200
    assert del_cap_resp.json()["deleted"] is True

    # Test BR-14 on legacy endpoint
    files3 = {"file": ("shelf_legacy_br14.jpg", io.BytesIO(b"\xff\xd8\xffimage"), "image/jpeg")}
    with patch("app.services.gemini_service.analyze_shelf_image", return_value=MOCK_EXTRACTED_PRODUCTS):
        create_resp3 = client.post(
            f"/api/v1/stores/{store.id}/shelf-jobs",
            headers=headers,
            files=files3,
            data={"zone": "Z", "aisle": "1"},
        )
    job_id3 = create_resp3.json()["id"]

    other_token = create_token(user_id="other_user_id", role="User", store_id="other_store_id")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    forbidden_resp = client.delete(f"/shelf/sessions/{job_id3}", headers=other_headers)
    assert forbidden_resp.status_code == 403

