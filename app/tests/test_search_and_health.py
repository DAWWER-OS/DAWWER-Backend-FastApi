import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.main import app
from app.models.map_models import MapNode, MapNodeType, StoreMap
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
def search_health_context(db: Session):
    """Sets up stores, maps, shelf nodes, and products for search and health probe tests."""
    user = User(
        id=str(uuid.uuid4()),
        email=f"search_owner_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Search Owner",
        role="StoreOwner",
        password_hash="test_hash",
    )
    db.add(user)
    db.commit()

    store = Store(
        id=str(uuid.uuid4()),
        name=f"Search Store {uuid.uuid4().hex[:4]}",
        owner_id=str(user.id),
        status="APPROVED",
        verification_status="APPROVED",
        is_active=True,
    )
    db.add(store)
    db.commit()

    # Create Revision 1 (Inactive draft history)
    map_rev1 = StoreMap(
        id=str(uuid.uuid4()),
        store_id=str(store.id),
        version=1,
        width_meters=50.0,
        height_meters=50.0,
        is_active=False,
    )
    # Create Revision 2 (Active published map)
    map_rev2 = StoreMap(
        id=str(uuid.uuid4()),
        store_id=str(store.id),
        version=2,
        width_meters=50.0,
        height_meters=50.0,
        is_active=True,
    )
    db.add_all([map_rev1, map_rev2])
    db.commit()

    # Active shelf node on active map_rev2
    active_shelf = MapNode(
        id=str(uuid.uuid4()),
        map_id=str(map_rev2.id),
        label="Active Shelf A1",
        node_type=MapNodeType.SHELF_TARGET.value,
        x_coord=10.0,
        y_coord=15.0,
        zone="Produce Zone",
        aisle="Aisle 1",
        is_active=True,
    )
    db.add(active_shelf)
    db.commit()

    # Product PLACED on active published map node -> availableInStore = True
    product_placed = StoreProduct(
        id=str(uuid.uuid4()),
        store_id=str(store.id),
        store_sku=f"SKU-PLACED-{uuid.uuid4().hex[:4]}",
        product_name="Fresh Apples",
        category="Produce",
        price=1.99,
        quantity=50,
        zone="Produce Zone",
        aisle="Aisle 1",
        map_target="Aisle 1 - Active Shelf A1 - Level 1",
        map_target_node_id=str(active_shelf.id),
        is_active=True,
    )
    # Product UNPLACED (no map_target_node_id) -> availableInStore = False
    product_unplaced = StoreProduct(
        id=str(uuid.uuid4()),
        store_id=str(store.id),
        store_sku=f"SKU-UNPLACED-{uuid.uuid4().hex[:4]}",
        product_name="Fresh Bananas",
        category="Produce",
        price=0.99,
        quantity=100,
        zone="Produce Zone",
        aisle="Aisle 1",
        map_target="Unassigned",
        map_target_node_id=None,
        is_active=True,
    )
    db.add_all([product_placed, product_unplaced])
    db.commit()

    context = {
        "store": store,
        "map_rev1": map_rev1,
        "map_rev2": map_rev2,
        "active_shelf": active_shelf,
        "product_placed": product_placed,
        "product_unplaced": product_unplaced,
    }

    yield context

    # Cleanup
    db.query(StoreProduct).filter(StoreProduct.store_id == store.id).delete(synchronize_session=False)
    db.query(MapNode).filter(MapNode.map_id.in_([map_rev1.id, map_rev2.id])).delete(synchronize_session=False)
    db.query(StoreMap).filter(StoreMap.store_id == store.id).delete(synchronize_session=False)
    db.query(Store).filter(Store.id == store.id).delete(synchronize_session=False)
    db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
    db.commit()


def test_search_catalog_with_available_in_store_flag(search_health_context):
    """Verifies GET /api/v1/products returns catalog items with availableInStore=True for placed products and False for unplaced products."""
    store = search_health_context["store"]

    response = client.get(f"/api/v1/products?storeId={store.id}&search=Fresh")

    assert response.status_code == 200
    products = response.json()
    assert isinstance(products, list)
    assert len(products) == 2

    # Map products by name
    prod_map = {p["product_name"]: p for p in products}

    assert "Fresh Apples" in prod_map
    assert prod_map["Fresh Apples"]["availableInStore"] is True

    assert "Fresh Bananas" in prod_map
    assert prod_map["Fresh Bananas"]["availableInStore"] is False


def test_get_floor_revisions_history(search_health_context):
    """Verifies GET /api/v1/floors/{floor_id}/revisions returns version history of floor map revisions."""
    store = search_health_context["store"]
    map_rev2 = search_health_context["map_rev2"]

    response = client.get(f"/api/v1/floors/{map_rev2.id}/revisions")

    assert response.status_code == 200
    revisions = response.json()
    assert isinstance(revisions, list)
    assert len(revisions) >= 2

    # Revisions should be ordered by version descending
    versions = [r["version"] for r in revisions]
    assert versions == sorted(versions, reverse=True)
    assert 2 in versions
    assert 1 in versions


def test_health_live_probe():
    """Verifies GET /health/live returns HTTP 200 OK with liveness metadata."""
    response = client.get("/health/live")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "live"
    assert "timestamp" in data


def test_health_ready_probe():
    """Verifies GET /health/ready returns HTTP 200 OK with database connection status."""
    response = client.get("/health/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"
