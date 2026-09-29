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
def test_navigation_store(db: Session):
    """Sets up a clean test store with an active StoreMap containing ENTRANCE_QR, products, and CASHIER."""
    test_user = User(
        id=str(uuid.uuid4()),
        email=f"nav_router_user_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Navigation Router Tester",
        role="StoreOwner",
        password_hash="test_hash",
    )
    db.add(test_user)
    db.commit()

    store = Store(
        id=str(uuid.uuid4()),
        name=f"Nav Store {uuid.uuid4().hex[:4]}",
        owner_id=str(test_user.id),
        status="APPROVED",
        verification_status="APPROVED",
        is_active=True,
    )
    db.add(store)
    db.commit()

    active_map = StoreMap(
        id=str(uuid.uuid4()),
        store_id=str(store.id),
        version=1,
        width_meters=50.0,
        height_meters=50.0,
        is_active=True,
    )
    db.add(active_map)
    db.commit()

    # Nodes
    entrance_id = str(uuid.uuid4())
    prod_a_node_id = str(uuid.uuid4())
    prod_b_node_id = str(uuid.uuid4())
    cashier_node_id = str(uuid.uuid4())

    entrance_node = MapNode(
        id=entrance_id,
        map_id=str(active_map.id),
        label="MAIN ENTRANCE QR",
        node_type=MapNodeType.ENTRANCE_QR.value,
        x_coord=0.0,
        y_coord=0.0,
        is_active=True,
    )
    prod_a_node = MapNode(
        id=prod_a_node_id,
        map_id=str(active_map.id),
        label="SHELF PROD A",
        node_type=MapNodeType.SHELF_TARGET.value,
        x_coord=20.0,
        y_coord=0.0,
        is_active=True,
    )
    prod_b_node = MapNode(
        id=prod_b_node_id,
        map_id=str(active_map.id),
        label="SHELF PROD B",
        node_type=MapNodeType.SHELF_TARGET.value,
        x_coord=10.0,
        y_coord=0.0,
        is_active=True,
    )
    cashier_node = MapNode(
        id=cashier_node_id,
        map_id=str(active_map.id),
        label="MAIN CASHIER CHECKOUT",
        node_type=MapNodeType.CASHIER.value,
        x_coord=30.0,
        y_coord=0.0,
        is_active=True,
    )
    db.add_all([entrance_node, prod_a_node, prod_b_node, cashier_node])
    db.commit()

    # Products
    prod_a = StoreProduct(
        id=str(uuid.uuid4()),
        store_id=str(store.id),
        store_sku=f"SKU-A-{uuid.uuid4().hex[:6]}",
        product_name="Product Alpha",
        category="Grocery",
        price=10.0,
        zone="Zone A",
        aisle="Aisle 1",
        map_target="PROD-A",
        map_target_node_id=prod_a_node_id,
        is_active=True,
    )
    prod_b = StoreProduct(
        id=str(uuid.uuid4()),
        store_id=str(store.id),
        store_sku=f"SKU-B-{uuid.uuid4().hex[:6]}",
        product_name="Product Beta",
        category="Grocery",
        price=15.0,
        zone="Zone A",
        aisle="Aisle 2",
        map_target="PROD-B",
        map_target_node_id=prod_b_node_id,
        is_active=True,
    )
    db.add_all([prod_a, prod_b])
    db.commit()

    context = {
        "store": store,
        "map": active_map,
        "entrance_node": entrance_node,
        "prod_a_node": prod_a_node,
        "prod_b_node": prod_b_node,
        "cashier_node": cashier_node,
        "prod_a": prod_a,
        "prod_b": prod_b,
    }

    yield context

    # Cleanup
    db.query(StoreProduct).filter(StoreProduct.store_id == store.id).delete(synchronize_session=False)
    db.query(MapEdge).filter(MapEdge.map_id == active_map.id).delete(synchronize_session=False)
    db.query(MapNode).filter(MapNode.map_id == active_map.id).delete(synchronize_session=False)
    db.query(StoreMap).filter(StoreMap.store_id == store.id).delete(synchronize_session=False)
    db.query(Store).filter(Store.id == store.id).delete(synchronize_session=False)
    db.query(User).filter(User.id == test_user.id).delete(synchronize_session=False)
    db.commit()


def test_post_shortest_entrance_qr_success(test_navigation_store):
    """Verifies POST /shortest resolves entrance QR code to a valid route response with steps."""
    store = test_navigation_store["store"]
    prod_a_node = test_navigation_store["prod_a_node"]

    payload = {
        "start_qr_code": "MAIN ENTRANCE QR",
        "target_node_id": str(prod_a_node.id),
        "avoid_crowded_edges": True,
    }

    response = client.post(
        f"/api/v1/stores/{store.id}/routes/shortest",
        json=payload,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["store_id"] == str(store.id)
    assert data["total_distance_meters"] >= 0.0
    assert data["estimated_time_seconds"] >= 1
    assert len(data["path_nodes"]) > 0
    assert len(data["steps"]) > 0
    assert any("MAIN ENTRANCE QR" in step_item["instruction"] for step_item in data["steps"])


def test_post_shortest_unreachable_destination_422(test_navigation_store):
    """Verifies POST /shortest with an unresolvable or invalid destination returns HTTP 422."""
    store = test_navigation_store["store"]

    payload = {
        "start_qr_code": "NON_EXISTENT_QR",
        "target_product_ids": ["non-existent-product-id-99999"],
    }

    response = client.post(
        f"/api/v1/stores/{store.id}/routes/shortest",
        json=payload,
    )

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data or "message" in data


def test_post_optimize_multi_stop_cashier(test_navigation_store):
    """Verifies POST /optimize reorders product items into an optimal route sequence terminating at cashier."""
    store = test_navigation_store["store"]
    prod_a = test_navigation_store["prod_a"]
    prod_b = test_navigation_store["prod_b"]

    payload = {
        "start_qr_code": "MAIN ENTRANCE QR",
        "product_ids": [str(prod_a.id), str(prod_b.id)],
        "avoid_crowded_edges": True,
    }

    response = client.post(
        f"/api/v1/stores/{store.id}/routes/optimize",
        json=payload,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["store_id"] == str(store.id)
    assert data["total_distance_meters"] > 0.0
    assert data["estimated_time_seconds"] >= 1
    assert isinstance(data["ordered_product_stops"], list)
    assert len(data["ordered_product_stops"]) == 2
    # Verify sequence visited nearest product B first (x=10) before product A (x=20)
    assert data["ordered_product_stops"][0] == str(prod_b.id)
    assert data["ordered_product_stops"][1] == str(prod_a.id)
    assert len(data["steps"]) > 0
    # Final step should arrive at cashier
    final_step = data["steps"][-1]
    assert "CASHIER" in final_step["instruction"].upper() or "CHECKOUT" in final_step["instruction"].upper() or "DESTINATION" in final_step["instruction"].upper()
