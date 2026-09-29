import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.main import app
from app.models.map_models import MapEdge, MapNode, MapNodeType, StoreMap
from app.models.product import StoreProduct
from app.models.store import Store
from app.models.user import User

client = TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def test_element_store(db: Session):
    """Sets up a clean test store and draft StoreMap floor for element CRUD testing."""
    test_user = User(
        id=str(uuid.uuid4()),
        email=f"element_user_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Map Element Tester",
        role="StoreOwner",
        password_hash="test_hash",
    )
    db.add(test_user)
    db.commit()

    store = Store(
        id=str(uuid.uuid4()),
        name=f"Element Store {uuid.uuid4().hex[:4]}",
        owner_id=str(test_user.id),
        status="APPROVED",
        verification_status="APPROVED",
        is_active=True,
    )
    db.add(store)
    db.commit()

    floor_map = StoreMap(
        id=str(uuid.uuid4()),
        store_id=str(store.id),
        version=1,
        width_meters=50.0,
        height_meters=50.0,
        is_active=False,
    )
    db.add(floor_map)
    db.commit()

    context = {
        "user": test_user,
        "store": store,
        "floor": floor_map,
    }

    yield context

    # Cleanup
    db.query(StoreProduct).filter(StoreProduct.store_id == store.id).delete(synchronize_session=False)
    db.query(MapEdge).filter(MapEdge.map_id == floor_map.id).delete(synchronize_session=False)
    db.query(MapNode).filter(MapNode.map_id == floor_map.id).delete(synchronize_session=False)
    db.query(StoreMap).filter(StoreMap.store_id == store.id).delete(synchronize_session=False)
    db.query(Store).filter(Store.id == store.id).delete(synchronize_session=False)
    db.query(User).filter(User.id == test_user.id).delete(synchronize_session=False)
    db.commit()


def test_post_create_map_element(test_element_store):
    """Verifies POST /api/v1/floors/{floor_id}/elements creates a single shelf element."""
    floor = test_element_store["floor"]

    payload = {
        "label": "Dairy Display Shelf A",
        "node_type": "SHELF_TARGET",
        "x_coord": 12.5,
        "y_coord": 8.0,
        "zone": "Dairy Section",
        "aisle": "Aisle 3",
    }

    response = client.post(
        f"/api/v1/floors/{floor.id}/elements",
        json=payload,
    )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["map_id"] == str(floor.id)
    assert data["label"] == "Dairy Display Shelf A"
    assert data["x_coord"] == 12.5
    assert data["y_coord"] == 8.0


def test_patch_update_map_element(test_element_store):
    """Verifies PATCH /api/v1/elements/{element_id} updates coordinates, type, or label."""
    floor = test_element_store["floor"]

    # 1. Create element first
    create_resp = client.post(
        f"/api/v1/floors/{floor.id}/elements",
        json={
            "label": "Initial Shelf",
            "node_type": "SHELF_TARGET",
            "x_coord": 5.0,
            "y_coord": 5.0,
        },
    )
    assert create_resp.status_code == 201
    element_id = create_resp.json()["id"]

    # 2. Update via PATCH
    update_payload = {
        "label": "Updated Bakery Shelf",
        "x_coord": 18.0,
        "y_coord": 15.0,
    }

    patch_resp = client.patch(
        f"/api/v1/elements/{element_id}",
        json=update_payload,
    )

    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["id"] == element_id
    assert data["label"] == "Updated Bakery Shelf"
    assert data["x_coord"] == 18.0
    assert data["y_coord"] == 15.0


def test_delete_map_element_blocked_when_products_placed(db: Session, test_element_store):
    """Verifies DELETE /api/v1/elements/{element_id} is blocked (HTTP 400) when products are placed on the shelf."""
    store = test_element_store["store"]
    floor = test_element_store["floor"]

    # 1. Create shelf element
    create_resp = client.post(
        f"/api/v1/floors/{floor.id}/elements",
        json={
            "label": "Occupied Shelf B",
            "node_type": "SHELF_TARGET",
            "x_coord": 25.0,
            "y_coord": 10.0,
        },
    )
    assert create_resp.status_code == 201
    element_id = create_resp.json()["id"]

    # 2. Place an active product on this shelf element
    prod = StoreProduct(
        id=str(uuid.uuid4()),
        store_id=str(store.id),
        store_sku=f"SKU-OCCUPIED-{uuid.uuid4().hex[:6]}",
        product_name="Product On Shelf",
        category="Snacks",
        price=5.0,
        zone="Snack Zone",
        aisle="Aisle 1",
        map_target="SNACK-01",
        map_target_node_id=element_id,
        is_active=True,
    )
    db.add(prod)
    db.commit()

    # 3. Attempt to delete shelf -> Must fail with HTTP 400
    del_resp = client.delete(f"/api/v1/elements/{element_id}")
    assert del_resp.status_code == 400
    data = del_resp.json()
    msg = data.get("detail") or data.get("message")
    assert "active product placements" in msg.lower() or "cannot delete" in msg.lower()


def test_delete_map_element_success_when_empty(test_element_store):
    """Verifies DELETE /api/v1/elements/{element_id} succeeds when the shelf contains no active product placements."""
    floor = test_element_store["floor"]

    # 1. Create empty shelf element
    create_resp = client.post(
        f"/api/v1/floors/{floor.id}/elements",
        json={
            "label": "Empty Temporary Shelf",
            "node_type": "SHELF_TARGET",
            "x_coord": 30.0,
            "y_coord": 20.0,
        },
    )
    assert create_resp.status_code == 201
    element_id = create_resp.json()["id"]

    # 2. Delete empty shelf
    del_resp = client.delete(f"/api/v1/elements/{element_id}")
    assert del_resp.status_code == 200
    data = del_resp.json()
    assert data["status"] == "success"
    assert element_id in data["message"] or data.get("element_id") == element_id
