import datetime
import uuid
import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.product import ProductLocation, StoreProduct
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


@pytest.fixture(autouse=True)
def cleanup():
    yield
    db = SessionLocal()
    try:
        test_prods = db.query(StoreProduct.id).filter(
            StoreProduct.store_sku.like("TEST-SKU-%")
        ).all()
        prod_ids = [p[0] for p in test_prods]
        if prod_ids:
            db.query(ProductLocation).filter(
                ProductLocation.product_id.in_(prod_ids)
            ).delete(synchronize_session=False)
        db.query(StoreProduct).filter(
            StoreProduct.store_sku.like("TEST-SKU-%")
        ).delete()
        db.commit()
    finally:
        db.close()


def test_create_product_success(store):
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "store_sku": "TEST-SKU-001",
        "barcode": "1234567890123",
        "product_name": "Organic Milk",
        "category": "Dairy",
        "price": 4.99,
        "stock_status": "IN_STOCK",
        "quantity": 50,
        "zone": "Zone A",
        "aisle": "Aisle 3",
        "rack": "Rack 1",
        "shelf": "Shelf 2",
        "map_target": "DAIRY-01",
    }

    response = client.post(
        f"/api/v1/stores/{store.id}/products", json=payload, headers=headers
    )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["store_sku"] == "TEST-SKU-001"
    assert data["zone"] == "Zone A"
    assert data["aisle"] == "Aisle 3"
    assert data["rack"] == "Rack 1"
    assert data["shelf"] == "Shelf 2"
    assert data["map_target"] == "DAIRY-01"


def test_create_product_duplicate_sku_fails(store):
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "store_sku": "TEST-SKU-002",
        "product_name": "Orange Juice",
        "category": "Beverages",
        "price": 3.50,
        "stock_status": "IN_STOCK",
        "quantity": 20,
        "zone": "Zone B",
        "aisle": "Aisle 1",
        "map_target": "BEV-01",
    }

    first_resp = client.post(
        f"/api/v1/stores/{store.id}/products", json=payload, headers=headers
    )
    assert first_resp.status_code == 201

    duplicate_resp = client.post(
        f"/api/v1/stores/{store.id}/products", json=payload, headers=headers
    )
    assert duplicate_resp.status_code == 400


def test_update_product_success(store):
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}
    create_payload = {
        "store_sku": "TEST-SKU-003",
        "product_name": "Cheddar Cheese",
        "category": "Dairy",
        "price": 5.00,
        "stock_status": "IN_STOCK",
        "quantity": 30,
        "zone": "Zone A",
        "aisle": "Aisle 2",
        "map_target": "DAIRY-02",
    }
    create_resp = client.post(
        f"/api/v1/stores/{store.id}/products", json=create_payload, headers=headers
    )
    assert create_resp.status_code == 201
    product_id = create_resp.json()["id"]

    update_payload = {
        "price": 6.50,
        "quantity": 45,
    }
    update_resp = client.put(
        f"/api/v1/stores/{store.id}/products/{product_id}",
        json=update_payload,
        headers=headers,
    )

    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["price"] == 6.50
    assert data["quantity"] == 45
    assert data["product_name"] == "Cheddar Cheese"


def test_get_product_details_and_list(store):
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "store_sku": "TEST-SKU-004",
        "product_name": "Whole Wheat Bread",
        "category": "Bakery",
        "price": 2.50,
        "stock_status": "IN_STOCK",
        "quantity": 15,
        "zone": "Zone C",
        "aisle": "Aisle 1",
        "map_target": "BAKE-01",
    }
    create_resp = client.post(
        f"/api/v1/stores/{store.id}/products", json=payload, headers=headers
    )
    assert create_resp.status_code == 201
    product_id = create_resp.json()["id"]

    get_resp = client.get(
        f"/api/v1/stores/{store.id}/products/{product_id}", headers=headers
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == product_id

    list_resp = client.get(f"/api/v1/stores/{store.id}/products", headers=headers)
    assert list_resp.status_code == 200
    products = list_resp.json()
    assert isinstance(products, list)
    assert any(p["id"] == product_id for p in products)


def test_store_isolation_br14_forbidden(store):
    other_token = create_token(
        user_id="unauthorized_user_888", role="User", store_id="other_store_999"
    )
    other_headers = {"Authorization": f"Bearer {other_token}"}
    payload = {
        "store_sku": "TEST-SKU-005",
        "product_name": "Forbidden Item",
        "category": "General",
        "price": 10.0,
        "stock_status": "IN_STOCK",
        "quantity": 5,
        "zone": "Zone D",
        "aisle": "Aisle 4",
        "map_target": "FORBID-01",
    }

    create_resp = client.post(
        f"/api/v1/stores/{store.id}/products", json=payload, headers=other_headers
    )
    assert create_resp.status_code == 403

    update_resp = client.put(
        f"/api/v1/stores/{store.id}/products/some-prod-id",
        json={"price": 20.0},
        headers=other_headers,
    )
    assert update_resp.status_code == 403


def test_delete_product_soft_delete_success(store):
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "store_sku": "TEST-SKU-DEL-001",
        "product_name": "Deactivatable Item",
        "category": "Snacks",
        "price": 12.50,
        "stock_status": "IN_STOCK",
        "quantity": 10,
        "zone": "Zone S",
        "aisle": "Aisle 2",
        "map_target": "SNACK-01",
    }

    create_resp = client.post(
        f"/api/v1/stores/{store.id}/products", json=payload, headers=headers
    )
    assert create_resp.status_code == 201
    product_id = create_resp.json()["id"]

    # Also add a product location record to verify BR-15 cascade deactivation
    db = SessionLocal()
    try:
        loc = ProductLocation(
            id=str(uuid.uuid4()),
            store_id=str(store.id),
            product_id=product_id,
            zone="Zone S",
            aisle="Aisle 2",
            is_active=True,
        )
        db.add(loc)
        db.commit()
    finally:
        db.close()

    # Call DELETE /api/v1/stores/{store_id}/products/{product_id}
    del_resp = client.delete(
        f"/api/v1/stores/{store.id}/products/{product_id}", headers=headers
    )
    assert del_resp.status_code == 200
    data = del_resp.json()
    assert data["message"] == "Product successfully deactivated"
    assert data["deleted"] is True
    assert data["product_id"] == product_id
    assert data["store_id"] == str(store.id)
    assert data["is_active"] is False
    assert data["hard_deleted"] is False
    assert data["product"]["is_active"] is False

    # Verify database state
    db = SessionLocal()
    try:
        db_prod = db.query(StoreProduct).filter(StoreProduct.id == product_id).first()
        assert db_prod is not None
        assert db_prod.is_active is False

        db_loc = db.query(ProductLocation).filter(ProductLocation.product_id == product_id).first()
        assert db_loc is not None
        assert db_loc.is_active is False
    finally:
        db.close()

    # Verify that executing GET /products (page refresh) strictly excludes the soft-deleted product
    list_resp = client.get(f"/api/v1/stores/{store.id}/products", headers=headers)
    assert list_resp.status_code == 200
    products = list_resp.json()
    assert not any(p["id"] == product_id for p in products), "Soft-deleted product must NOT appear in default product list on refresh"

    # Verify single GET returns 404 unless include_inactive=True is specified
    single_resp = client.get(f"/api/v1/stores/{store.id}/products/{product_id}", headers=headers)
    assert single_resp.status_code == 404

    single_resp_inactive = client.get(
        f"/api/v1/stores/{store.id}/products/{product_id}?include_inactive=true",
        headers=headers,
    )
    assert single_resp_inactive.status_code == 200
    assert single_resp_inactive.json()["id"] == product_id


def test_delete_product_hard_delete_success(store):
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "store_sku": "TEST-SKU-DEL-002",
        "product_name": "Hard Delete Item",
        "category": "Snacks",
        "price": 8.00,
        "stock_status": "IN_STOCK",
        "quantity": 5,
        "zone": "Zone H",
        "aisle": "Aisle 1",
        "map_target": "HARD-01",
    }

    create_resp = client.post(
        f"/api/v1/stores/{store.id}/products", json=payload, headers=headers
    )
    assert create_resp.status_code == 201
    product_id = create_resp.json()["id"]

    # Call DELETE with hard_delete=True
    del_resp = client.delete(
        f"/api/v1/stores/{store.id}/products/{product_id}?hard_delete=true", headers=headers
    )
    assert del_resp.status_code == 200
    data = del_resp.json()
    assert data["message"] == "Product permanently deleted"
    assert data["deleted"] is True
    assert data["product_id"] == product_id
    assert data["hard_deleted"] is True
    assert data["is_active"] is False
    assert data["product"] is None

    # Verify product is removed from database
    db = SessionLocal()
    try:
        db_prod = db.query(StoreProduct).filter(StoreProduct.id == product_id).first()
        assert db_prod is None
    finally:
        db.close()

    # Verify GET excludes hard-deleted product permanently
    list_resp = client.get(f"/api/v1/stores/{store.id}/products", headers=headers)
    assert list_resp.status_code == 200
    assert not any(p["id"] == product_id for p in list_resp.json())

    single_resp = client.get(f"/api/v1/stores/{store.id}/products/{product_id}", headers=headers)
    assert single_resp.status_code == 404


def test_delete_product_not_found_404(store):
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}
    non_existent_id = str(uuid.uuid4())

    del_resp = client.delete(
        f"/api/v1/stores/{store.id}/products/{non_existent_id}", headers=headers
    )
    assert del_resp.status_code == 404
    data = del_resp.json()
    msg = data.get("message") or data.get("detail")
    assert msg == "Product not found"


def test_delete_product_store_isolation_br14_unauthorized_token(store):
    other_token = create_token(
        user_id="unauthorized_user_777", role="User", store_id="other_store_888"
    )
    other_headers = {"Authorization": f"Bearer {other_token}"}

    del_resp = client.delete(
        f"/api/v1/stores/{store.id}/products/some-prod-id", headers=other_headers
    )
    assert del_resp.status_code == 403
    data = del_resp.json()
    msg = data.get("message", "") or data.get("detail", "")
    assert "BR-14" in msg or "Operation not permitted" in msg


def test_delete_product_store_isolation_br14_cross_store_product(store):
    # Merchant of store tries to delete a product that belongs to another store
    token = create_token(user_id=str(store.owner_id), store_id=str(store.id))
    headers = {"Authorization": f"Bearer {token}"}

    db = SessionLocal()
    other_store_id = str(uuid.uuid4())
    other_prod_id = str(uuid.uuid4())
    try:
        other_store = Store(
            id=other_store_id,
            name="Other Store Isolated",
            owner_id=str(store.owner_id),
            status="APPROVED",
            verification_status="APPROVED",
            is_active=True,
        )
        db.add(other_store)
        db.commit()

        other_product = StoreProduct(
            id=other_prod_id,
            store_id=other_store_id,
            store_sku="TEST-SKU-CROSS-001",
            product_name="Other Store Item",
            category="Other",
            price=15.00,
            stock_status="IN_STOCK",
            quantity=10,
            zone="Zone X",
            aisle="Aisle X",
            map_target="TARGET-X",
        )
        db.add(other_product)
        db.commit()
    finally:
        db.close()

    try:
        del_resp = client.delete(
            f"/api/v1/stores/{store.id}/products/{other_prod_id}", headers=headers
        )
        assert del_resp.status_code == 403
        data = del_resp.json()
        msg = data.get("message", "") or data.get("detail", "")
        assert "another store" in msg or "BR-14" in msg
    finally:
        cleanup_db = SessionLocal()
        try:
            cleanup_db.query(StoreProduct).filter(StoreProduct.id == other_prod_id).delete()
            cleanup_db.query(Store).filter(Store.id == other_store_id).delete()
            cleanup_db.commit()
        finally:
            cleanup_db.close()
