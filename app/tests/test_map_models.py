import uuid
import pytest
from app.db.session import SessionLocal
from app.models.map_models import MapEdge, MapNode, MapNodeType, StoreMap
from app.models.product import ProductLocation, StoreProduct
from app.models.store import Store
from app.models.user import User


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def test_store(db_session):
    store = db_session.query(Store).first()
    if not store:
        user = db_session.query(User).first()
        if not user:
            user = User(
                id=str(uuid.uuid4()),
                email=f"map_test_user_{uuid.uuid4().hex[:6]}@example.com",
                full_name="Map Test User",
                role="StoreOwner",
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)

        store = Store(
            id=str(uuid.uuid4()),
            name=f"Map Test Store {uuid.uuid4().hex[:4]}",
            owner_id=str(user.id),
            status="APPROVED",
            verification_status="APPROVED",
            is_active=True,
        )
        db_session.add(store)
        db_session.commit()
        db_session.refresh(store)
    return store


def test_create_store_map_and_graph_relationships(db_session, test_store):
    # 1. Create a StoreMap
    store_map = StoreMap(
        id=str(uuid.uuid4()),
        store_id=str(test_store.id),
        version=1,
        floor_plan_image_url="https://example.com/floorplans/floor_1.png",
        width_meters=60.0,
        height_meters=45.0,
        is_active=True,
    )
    db_session.add(store_map)
    db_session.commit()
    db_session.refresh(store_map)

    assert store_map.id is not None
    assert store_map.store_id == str(test_store.id)
    assert store_map.version == 1
    assert store_map.width_meters == 60.0
    assert store_map.height_meters == 45.0
    assert store_map.is_active is True
    assert store_map.created_at is not None

    # 2. Create MapNodes
    entrance_node = MapNode(
        id=str(uuid.uuid4()),
        map_id=str(store_map.id),
        node_type=MapNodeType.ENTRANCE_QR.value,
        label="Main Entrance QR",
        x_coord=0.0,
        y_coord=0.0,
        zone="Entrance",
        aisle=None,
        is_active=True,
    )
    junction_node = MapNode(
        id=str(uuid.uuid4()),
        map_id=str(store_map.id),
        node_type=MapNodeType.AISLE_JUNCTION.value,
        label="Aisle 1 Junction",
        x_coord=10.0,
        y_coord=0.0,
        zone="Zone A",
        aisle="Aisle 1",
        is_active=True,
    )
    shelf_node = MapNode(
        id=str(uuid.uuid4()),
        map_id=str(store_map.id),
        node_type=MapNodeType.SHELF_TARGET.value,
        label="Aisle 1 - Coffee Rack",
        x_coord=10.0,
        y_coord=15.0,
        zone="Zone A",
        aisle="Aisle 1",
        is_active=True,
    )
    cashier_node = MapNode(
        id=str(uuid.uuid4()),
        map_id=str(store_map.id),
        node_type=MapNodeType.CASHIER.value,
        label="Cashier 1",
        x_coord=30.0,
        y_coord=0.0,
        zone="Checkout",
        aisle=None,
        is_active=True,
    )

    db_session.add_all([entrance_node, junction_node, shelf_node, cashier_node])
    db_session.commit()

    # 3. Create MapEdges
    edge_1 = MapEdge(
        id=str(uuid.uuid4()),
        map_id=str(store_map.id),
        from_node_id=str(entrance_node.id),
        to_node_id=str(junction_node.id),
        distance_meters=10.0,
        weight=1.0,
        is_accessible=True,
        is_blocked=False,
    )
    edge_2 = MapEdge(
        id=str(uuid.uuid4()),
        map_id=str(store_map.id),
        from_node_id=str(junction_node.id),
        to_node_id=str(shelf_node.id),
        distance_meters=15.0,
        weight=1.2,
        is_accessible=True,
        is_blocked=False,
    )
    edge_3 = MapEdge(
        id=str(uuid.uuid4()),
        map_id=str(store_map.id),
        from_node_id=str(junction_node.id),
        to_node_id=str(cashier_node.id),
        distance_meters=20.0,
        weight=1.0,
        is_accessible=True,
        is_blocked=True,
    )

    db_session.add_all([edge_1, edge_2, edge_3])
    db_session.commit()

    # 4. Verify StoreMap relationships
    db_session.refresh(store_map)
    assert len(store_map.nodes) == 4
    assert len(store_map.edges) == 3

    # 5. Verify Node and Edge relationships
    db_session.refresh(junction_node)
    assert len(junction_node.incoming_edges) == 1
    assert junction_node.incoming_edges[0].from_node.label == "Main Entrance QR"
    assert len(junction_node.outgoing_edges) == 2

    # 6. Verify ProductLocation referencing shelf_node
    product_loc = ProductLocation(
        id=str(uuid.uuid4()),
        store_id=str(test_store.id),
        zone="Zone A",
        aisle="Aisle 1",
        rack="Rack 3",
        shelf="Shelf B",
        map_target="COFFEE-RACK-01",
        map_target_node_id=str(shelf_node.id),
        is_active=True,
    )
    db_session.add(product_loc)
    db_session.commit()
    db_session.refresh(product_loc)

    assert product_loc.map_target_node_id == str(shelf_node.id)
    assert product_loc.map_target_node.label == "Aisle 1 - Coffee Rack"
    assert len(shelf_node.product_locations) >= 1

    # 7. Verify StoreProduct referencing shelf_node
    product = StoreProduct(
        id=str(uuid.uuid4()),
        store_id=str(test_store.id),
        store_sku=f"SKU-{uuid.uuid4().hex[:8]}",
        product_name="Dark Roast Coffee 500g",
        category="Beverages",
        price=18.5,
        zone="Zone A",
        aisle="Aisle 1",
        rack="Rack 3",
        shelf="Shelf B",
        map_target="COFFEE-RACK-01",
        map_target_node_id=str(shelf_node.id),
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    assert product.map_target_node_id == str(shelf_node.id)
    assert product.map_target_node.label == "Aisle 1 - Coffee Rack"
    assert len(shelf_node.store_products) >= 1

    # Cleanup test artifacts
    db_session.delete(product)
    db_session.delete(product_loc)
    db_session.delete(edge_1)
    db_session.delete(edge_2)
    db_session.delete(edge_3)
    db_session.delete(entrance_node)
    db_session.delete(junction_node)
    db_session.delete(shelf_node)
    db_session.delete(cashier_node)
    db_session.delete(store_map)
    db_session.commit()
