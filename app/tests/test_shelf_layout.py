import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.main import app
from app.models.map_models import MapNode, MapNodeType, StoreMap
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
def test_shelf_layout_stores(db: Session):
    """Sets up clean test stores and shelf elements for shelf layout configuration testing."""
    user_a = User(
        id=str(uuid.uuid4()),
        email=f"shelf_owner_a_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Shelf Owner A",
        role="StoreOwner",
        password_hash="test_hash",
    )
    user_b = User(
        id=str(uuid.uuid4()),
        email=f"shelf_owner_b_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Shelf Owner B",
        role="StoreOwner",
        password_hash="test_hash",
    )
    db.add_all([user_a, user_b])
    db.commit()

    store_a = Store(
        id=str(uuid.uuid4()),
        name=f"Shelf Store A {uuid.uuid4().hex[:4]}",
        owner_id=str(user_a.id),
        status="APPROVED",
        verification_status="APPROVED",
        is_active=True,
    )
    store_b = Store(
        id=str(uuid.uuid4()),
        name=f"Shelf Store B {uuid.uuid4().hex[:4]}",
        owner_id=str(user_b.id),
        status="APPROVED",
        verification_status="APPROVED",
        is_active=True,
    )
    db.add_all([store_a, store_b])
    db.commit()

    map_a = StoreMap(
        id=str(uuid.uuid4()),
        store_id=str(store_a.id),
        version=1,
        width_meters=50.0,
        height_meters=50.0,
        is_active=True,
    )
    map_b = StoreMap(
        id=str(uuid.uuid4()),
        store_id=str(store_b.id),
        version=1,
        width_meters=50.0,
        height_meters=50.0,
        is_active=True,
    )
    db.add_all([map_a, map_b])
    db.commit()

    shelf_a = MapNode(
        id=str(uuid.uuid4()),
        map_id=str(map_a.id),
        label="Shelf Main A1",
        node_type=MapNodeType.SHELF_TARGET.value,
        x_coord=15.0,
        y_coord=10.0,
        zone="Zone A",
        aisle="Aisle 1",
        is_active=True,
    )
    shelf_b = MapNode(
        id=str(uuid.uuid4()),
        map_id=str(map_b.id),
        label="Shelf Other B1",
        node_type=MapNodeType.SHELF_TARGET.value,
        x_coord=25.0,
        y_coord=20.0,
        zone="Zone B",
        aisle="Aisle 2",
        is_active=True,
    )
    db.add_all([shelf_a, shelf_b])
    db.commit()

    context = {
        "store_a": store_a,
        "store_b": store_b,
        "map_a": map_a,
        "map_b": map_b,
        "shelf_a": shelf_a,
        "shelf_b": shelf_b,
    }

    yield context

    # Cleanup
    db.query(MapNode).filter(MapNode.map_id.in_([map_a.id, map_b.id])).delete(synchronize_session=False)
    db.query(StoreMap).filter(StoreMap.store_id.in_([store_a.id, store_b.id])).delete(synchronize_session=False)
    db.query(Store).filter(Store.id.in_([store_a.id, store_b.id])).delete(synchronize_session=False)
    db.query(User).filter(User.id.in_([user_a.id, user_b.id])).delete(synchronize_session=False)
    db.commit()


def test_get_shelf_layout_success(test_shelf_layout_stores):
    """Verifies GET /api/v1/shelves/{shelf_id}/layout retrieves shelf physical layout and access points."""
    shelf_a = test_shelf_layout_stores["shelf_a"]

    response = client.get(f"/api/v1/shelves/{shelf_a.id}/layout")

    assert response.status_code == 200
    data = response.json()
    assert data["shelf_id"] == str(shelf_a.id)
    assert data["label"] == "Shelf Main A1"
    assert data["sides"] in (1, 2)
    assert data["sections_count"] >= 1
    assert data["levels_count"] >= 1
    assert isinstance(data["access_points"], list)
    assert len(data["access_points"]) >= 1
    assert "x_coord" in data["access_points"][0]
    assert "y_coord" in data["access_points"][0]


def test_patch_update_shelf_layout_and_access_points(test_shelf_layout_stores):
    """Verifies PATCH /api/v1/shelves/{shelf_id}/layout modifies physical levels, sides, and access points."""
    shelf_a = test_shelf_layout_stores["shelf_a"]

    update_payload = {
        "sides": 1,
        "sections_count": 6,
        "levels_count": 7,
        "x_coord": 16.0,
        "y_coord": 11.0,
    }

    response = client.patch(
        f"/api/v1/shelves/{shelf_a.id}/layout",
        json=update_payload,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["shelf_id"] == str(shelf_a.id)
    assert data["sides"] == 1
    assert data["sections_count"] == 6
    assert data["levels_count"] == 7
    assert data["x_coord"] == 16.0
    assert data["y_coord"] == 11.0
    assert len(data["access_points"]) == 1
    assert data["access_points"][0]["side"] == "Side A"


def test_shelf_layout_store_isolation_br14_forbidden(test_shelf_layout_stores):
    """Verifies store isolation (BR-14) prevents unauthorized modification of another store's shelf layout."""
    store_a = test_shelf_layout_stores["store_a"]
    shelf_b = test_shelf_layout_stores["shelf_b"]  # Belongs to Store B

    # Attempt to access Store B's shelf layout using Store A's scoping
    response = client.get(
        f"/api/v1/stores/{store_a.id}/shelves/{shelf_b.id}/layout"
    )

    assert response.status_code == 403
    data = response.json()
    msg = data.get("detail") or data.get("message")
    assert "BR-14" in msg or "isolation" in msg.lower() or "denied" in msg.lower()
