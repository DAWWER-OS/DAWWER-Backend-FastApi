import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.main import app
from app.models.map_models import MapNode, MapNodeType, StoreMap
from app.models.product import ProductLocation, StoreProduct
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
def placement_test_context(db: Session):
    """Sets up store owners, stores, draft maps, shelf nodes, and catalog products for placement testing."""
    user_a = User(
        id=str(uuid.uuid4()),
        email=f"placement_owner_a_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Placement Owner A",
        role="StoreOwner",
        password_hash="test_hash",
    )
    user_b = User(
        id=str(uuid.uuid4()),
        email=f"placement_owner_b_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Placement Owner B",
        role="StoreOwner",
        password_hash="test_hash",
    )
    db.add_all([user_a, user_b])
    db.commit()

    store_a = Store(
        id=str(uuid.uuid4()),
        name=f"Placement Store A {uuid.uuid4().hex[:4]}",
        owner_id=str(user_a.id),
        status="APPROVED",
        verification_status="APPROVED",
        is_active=True,
    )
    store_b = Store(
        id=str(uuid.uuid4()),
        name=f"Placement Store B {uuid.uuid4().hex[:4]}",
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

    shelf_a1 = MapNode(
        id=str(uuid.uuid4()),
        map_id=str(map_a.id),
        label="Shelf Aisle 1 Bay A",
        node_type=MapNodeType.SHELF_TARGET.value,
        x_coord=12.5,
        y_coord=8.0,
        zone="Grocery Zone",
        aisle="Aisle 1",
        is_active=True,
    )
    shelf_a2 = MapNode(
        id=str(uuid.uuid4()),
        map_id=str(map_a.id),
        label="Shelf Aisle 1 Bay B",
        node_type=MapNodeType.SHELF_TARGET.value,
        x_coord=12.5,
        y_coord=14.0,
        zone="Grocery Zone",
        aisle="Aisle 1",
        is_active=True,
    )
    shelf_b1 = MapNode(
        id=str(uuid.uuid4()),
        map_id=str(map_b.id),
        label="Shelf B-101",
        node_type=MapNodeType.SHELF_TARGET.value,
        x_coord=30.0,
        y_coord=25.0,
        zone="Zone B",
        aisle="Aisle B1",
        is_active=True,
    )
    db.add_all([shelf_a1, shelf_a2, shelf_b1])
    db.commit()

    product_a = StoreProduct(
        id=str(uuid.uuid4()),
        store_id=str(store_a.id),
        store_sku=f"SKU-A-{uuid.uuid4().hex[:4]}",
        product_name="Organic Milk 1L",
        category="Dairy",
        price=3.99,
        zone="Grocery Zone",
        aisle="Aisle 1",
        map_target="Unassigned",
        map_target_node_id=None,
        is_active=True,
    )
    product_b = StoreProduct(
        id=str(uuid.uuid4()),
        store_id=str(store_b.id),
        store_sku=f"SKU-B-{uuid.uuid4().hex[:4]}",
        product_name="Cheddar Cheese 500g",
        category="Dairy",
        price=5.49,
        zone="Dairy Zone",
        aisle="Aisle 4",
        map_target="Unassigned",
        map_target_node_id=None,
        is_active=True,
    )
    db.add_all([product_a, product_b])
    db.commit()

    context = {
        "store_a": store_a,
        "store_b": store_b,
        "map_a": map_a,
        "map_b": map_b,
        "shelf_a1": shelf_a1,
        "shelf_a2": shelf_a2,
        "shelf_b1": shelf_b1,
        "product_a": product_a,
        "product_b": product_b,
    }

    yield context

    # Cleanup
    db.query(ProductLocation).filter(ProductLocation.store_id.in_([store_a.id, store_b.id])).delete(synchronize_session=False)
    db.query(StoreProduct).filter(StoreProduct.store_id.in_([store_a.id, store_b.id])).delete(synchronize_session=False)
    db.query(MapNode).filter(MapNode.map_id.in_([map_a.id, map_b.id])).delete(synchronize_session=False)
    db.query(StoreMap).filter(StoreMap.store_id.in_([store_a.id, store_b.id])).delete(synchronize_session=False)
    db.query(Store).filter(Store.id.in_([store_a.id, store_b.id])).delete(synchronize_session=False)
    db.query(User).filter(User.id.in_([user_a.id, user_b.id])).delete(synchronize_session=False)
    db.commit()


def test_create_product_placement_success(placement_test_context, db: Session):
    """Verifies POST /api/v1/stores/{store_id}/placements creates placement link & formats location code."""
    store_a = placement_test_context["store_a"]
    shelf_a1 = placement_test_context["shelf_a1"]
    product_a = placement_test_context["product_a"]

    payload = {
        "product_id": str(product_a.id),
        "shelf_id": str(shelf_a1.id),
        "section": "2",
        "level": "3",
        "aisle": "Aisle 1",
        "zone": "Grocery Zone",
    }

    response = client.post(
        f"/api/v1/stores/{store_a.id}/placements",
        json=payload,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["product_id"] == str(product_a.id)
    assert data["store_id"] == str(store_a.id)
    assert data["shelf_id"] == str(shelf_a1.id)
    assert data["section"] == "2"
    assert data["level"] == "3"
    assert data["x_coord"] == 12.5
    assert data["y_coord"] == 8.0
    assert "location_code" in data
    assert "Aisle 1" in data["location_code"]
    assert "Level 3" in data["location_code"]

    # Verify catalog product link was updated
    db.refresh(product_a)
    assert product_a.map_target_node_id == str(shelf_a1.id)


def test_update_product_placement_level_and_shelf(placement_test_context, db: Session):
    """Verifies PATCH /api/v1/placements/{placement_id} updates shelf slot, level, and location mapping."""
    store_a = placement_test_context["store_a"]
    shelf_a1 = placement_test_context["shelf_a1"]
    shelf_a2 = placement_test_context["shelf_a2"]
    product_a = placement_test_context["product_a"]

    # Create initial placement
    create_payload = {
        "product_id": str(product_a.id),
        "shelf_id": str(shelf_a1.id),
        "section": "1",
        "level": "1",
    }
    create_res = client.post(f"/api/v1/stores/{store_a.id}/placements", json=create_payload)
    assert create_res.status_code == 201
    placement_id = create_res.json()["placement_id"]

    # Move product to shelf_a2 and level 4
    update_payload = {
        "shelf_id": str(shelf_a2.id),
        "section": "3",
        "level": "4",
    }
    patch_res = client.patch(
        f"/api/v1/stores/{store_a.id}/placements/{placement_id}",
        json=update_payload,
    )

    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["placement_id"] == placement_id
    assert data["shelf_id"] == str(shelf_a2.id)
    assert data["section"] == "3"
    assert data["level"] == "4"
    assert data["x_coord"] == 12.5
    assert data["y_coord"] == 14.0

    # Verify catalog product target node updated
    db.refresh(product_a)
    assert product_a.map_target_node_id == str(shelf_a2.id)


def test_delete_product_placement_preserves_catalog_product(placement_test_context, db: Session):
    """Verifies DELETE /api/v1/placements/{placement_id} unlinks map placement while preserving catalog item."""
    store_a = placement_test_context["store_a"]
    shelf_a1 = placement_test_context["shelf_a1"]
    product_a = placement_test_context["product_a"]

    create_res = client.post(
        f"/api/v1/stores/{store_a.id}/placements",
        json={"product_id": str(product_a.id), "shelf_id": str(shelf_a1.id)},
    )
    placement_id = create_res.json()["placement_id"]

    # Delete placement
    del_res = client.delete(f"/api/v1/stores/{store_a.id}/placements/{placement_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # Verify product in catalog is unlinked but STILL EXISTS
    db.refresh(product_a)
    assert product_a is not None
    assert product_a.map_target_node_id is None


def test_get_product_locations(placement_test_context):
    """Verifies GET /api/v1/stores/{store_id}/products/{product_id}/locations returns physical map coordinates."""
    store_a = placement_test_context["store_a"]
    shelf_a1 = placement_test_context["shelf_a1"]
    product_a = placement_test_context["product_a"]

    client.post(
        f"/api/v1/stores/{store_a.id}/placements",
        json={"product_id": str(product_a.id), "shelf_id": str(shelf_a1.id), "level": "2"},
    )

    response = client.get(f"/api/v1/stores/{store_a.id}/products/{product_a.id}/locations")
    assert response.status_code == 200
    locations = response.json()
    assert isinstance(locations, list)
    assert len(locations) >= 1
    loc = locations[0]
    assert loc["product_id"] == str(product_a.id)
    assert loc["shelf_id"] == str(shelf_a1.id)
    assert loc["x_coord"] == 12.5
    assert loc["y_coord"] == 8.0


def test_product_placement_store_isolation_br14_forbidden(placement_test_context):
    """Verifies store isolation (BR-14) blocks unauthorized cross-store product placements."""
    store_a = placement_test_context["store_a"]
    shelf_a1 = placement_test_context["shelf_a1"]
    product_b = placement_test_context["product_b"]  # Belongs to Store B

    # Attempt to place Store B's product onto Store A's shelf node
    response = client.post(
        f"/api/v1/stores/{store_a.id}/placements",
        json={"product_id": str(product_b.id), "shelf_id": str(shelf_a1.id)},
    )

    assert response.status_code == 403
    data = response.json()
    msg = data.get("detail") or data.get("message")
    assert "BR-14" in msg or "isolation" in msg.lower() or "denied" in msg.lower()
