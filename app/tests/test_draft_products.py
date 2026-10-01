import datetime
import uuid
import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.product import StoreProduct
from app.models.shelf_job import DraftProduct, ShelfJob
from app.models.store import Store
from app.models.user import User

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


@pytest.fixture
def sample_draft(store):
    db = SessionLocal()
    try:
        job = ShelfJob(
            id=str(uuid.uuid4()),
            store_id=store.id,
            status="REVIEW_REQUIRED",
            zone="Zone A",
            aisle="Aisle 1",
        )
        db.add(job)
        db.commit()

        draft = DraftProduct(
            id=str(uuid.uuid4()),
            store_id=store.id,
            shelf_job_id=job.id,
            proposed_name="Almarai Fresh Milk 2L",
            estimated_price=11.5,
            category_hint="Dairy",
            pack_size="2L",
            barcode_detected=f"628100{str(uuid.uuid4())[:6]}",
            confidence_score=0.95,
            zone="Zone A",
            aisle="Aisle 1",
            status="PENDING_REVIEW",
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        return draft
    finally:
        db.close()


def test_list_draft_products(store, sample_draft):
    token = create_token(user_id=store.owner_id, store_id=store.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get(f"/api/v1/stores/{store.id}/draft-products", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(d["id"] == sample_draft.id for d in data)


def test_get_single_draft_product(store, sample_draft):
    token = create_token(user_id=store.owner_id, store_id=store.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get(f"/api/v1/stores/{store.id}/draft-products/{sample_draft.id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sample_draft.id
    assert data["proposed_name"] == sample_draft.proposed_name


def test_update_draft_product(store, sample_draft):
    token = create_token(user_id=store.owner_id, store_id=store.id)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "proposed_name": "Almarai Full Fat Milk 2L",
        "estimated_price": 12.0,
    }
    response = client.put(
        f"/api/v1/stores/{store.id}/draft-products/{sample_draft.id}",
        json=payload,
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["proposed_name"] == "Almarai Full Fat Milk 2L"
    assert data["estimated_price"] == 12.0


def test_approve_draft_product_creates_store_product(store, sample_draft):
    token = create_token(user_id=store.owner_id, store_id=store.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        f"/api/v1/stores/{store.id}/draft-products/{sample_draft.id}/approve",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "APPROVED"
    assert data["store_product_id"] is not None

    # Verify that the StoreProduct exists in the DB
    db = SessionLocal()
    try:
        prod = db.query(StoreProduct).filter(StoreProduct.id == data["store_product_id"]).first()
        assert prod is not None
        assert prod.product_name == sample_draft.proposed_name
        assert prod.store_id == store.id
    finally:
        db.close()


def test_reject_draft_product(store, sample_draft):
    token = create_token(user_id=store.owner_id, store_id=store.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        f"/api/v1/stores/{store.id}/draft-products/{sample_draft.id}/reject",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "REJECTED"
    assert data["deleted"] is True
    assert data["product_id"] == sample_draft.id

    # Verify that listing draft products excludes REJECTED by default (prevents reappearing upon refresh)
    list_resp = client.get(f"/api/v1/stores/{store.id}/draft-products", headers=headers)
    assert list_resp.status_code == 200
    assert not any(d["id"] == sample_draft.id for d in list_resp.json())


def test_delete_draft_product_success(store, sample_draft):
    token = create_token(user_id=store.owner_id, store_id=store.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Delete draft product item
    del_resp = client.delete(
        f"/api/v1/stores/{store.id}/draft-products/{sample_draft.id}",
        headers=headers,
    )
    assert del_resp.status_code == 200
    del_data = del_resp.json()
    assert del_data["deleted"] is True
    assert del_data["product_id"] == sample_draft.id
    assert del_data["draft_id"] == sample_draft.id
    assert del_data["hard_deleted"] is True

    # Verify excluded permanently from GET
    list_resp = client.get(f"/api/v1/stores/{store.id}/draft-products", headers=headers)
    assert list_resp.status_code == 200
    assert not any(d["id"] == sample_draft.id for d in list_resp.json())

    single_resp = client.get(f"/api/v1/stores/{store.id}/draft-products/{sample_draft.id}", headers=headers)
    assert single_resp.status_code == 404


def test_delete_shelf_job_item_route(store, sample_draft):
    token = create_token(user_id=store.owner_id, store_id=store.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Delete via shelf job item route
    del_resp = client.delete(
        f"/api/v1/stores/{store.id}/shelf-jobs/{sample_draft.shelf_job_id}/items/{sample_draft.id}",
        headers=headers,
    )
    assert del_resp.status_code == 200
    del_data = del_resp.json()
    assert del_data["deleted"] is True
    assert del_data["product_id"] == sample_draft.id


def test_draft_product_isolation_br14_forbidden(store, sample_draft):
    other_token = create_token(user_id=str(uuid.uuid4()), role="User", store_id=str(uuid.uuid4()))
    headers = {"Authorization": f"Bearer {other_token}"}

    # Attempt to list drafts of a store not authorized
    response = client.get(f"/api/v1/stores/{store.id}/draft-products", headers=headers)
    assert response.status_code == 403

    # Attempt to approve draft of a store not authorized
    approve_resp = client.post(
        f"/api/v1/stores/{store.id}/draft-products/{sample_draft.id}/approve",
        headers=headers,
    )
    assert approve_resp.status_code == 403
