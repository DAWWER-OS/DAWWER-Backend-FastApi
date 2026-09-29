import uuid
from fastapi import HTTPException
import pytest
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.map_models import MapEdge, MapNode, MapNodeType, StoreMap
from app.models.store import Store
from app.models.user import User
from app.services.map_service import MapService, MapValidationError


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def test_stores(db: Session):
    """Provides two clean test stores for tenant isolation and lifecycle testing."""
    test_user = User(
        id=str(uuid.uuid4()),
        email=f"map_svc_user_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Map Service Tester",
        role="StoreOwner",
        password_hash="test_hash",
    )
    db.add(test_user)
    db.commit()

    store_a = Store(
        id=str(uuid.uuid4()),
        name=f"Store A {uuid.uuid4().hex[:4]}",
        owner_id=str(test_user.id),
        status="APPROVED",
        verification_status="APPROVED",
        is_active=True,
    )
    store_b = Store(
        id=str(uuid.uuid4()),
        name=f"Store B {uuid.uuid4().hex[:4]}",
        owner_id=str(test_user.id),
        status="APPROVED",
        verification_status="APPROVED",
        is_active=True,
    )
    db.add_all([store_a, store_b])
    db.commit()

    yield store_a, store_b

    # Cleanup
    db.query(StoreMap).filter(StoreMap.store_id.in_([store_a.id, store_b.id])).delete(synchronize_session=False)
    db.query(Store).filter(Store.id.in_([store_a.id, store_b.id])).delete(synchronize_session=False)
    db.query(User).filter(User.id == test_user.id).delete(synchronize_session=False)
    db.commit()


def test_get_or_create_draft_map(db: Session, test_stores):
    """Verifies auto-creation of a draft map for a new store and retrieving existing draft."""
    store_a, _ = test_stores

    # 1. Create first draft map
    draft_map_1 = MapService.get_or_create_draft_map(db, str(store_a.id))
    assert draft_map_1 is not None
    assert str(draft_map_1.store_id) == str(store_a.id)
    assert draft_map_1.is_active is False
    assert draft_map_1.version == 1
    assert draft_map_1.width_meters == 50.0
    assert draft_map_1.height_meters == 50.0

    # 2. Calling again must return existing draft map, not create a duplicate
    draft_map_2 = MapService.get_or_create_draft_map(db, str(store_a.id))
    assert draft_map_2.id == draft_map_1.id
    assert draft_map_2.version == draft_map_1.version


def test_save_elements_batch_success(db: Session, test_stores):
    """Verifies atomic creation, update, and deletion of map nodes and edges."""
    store_a, _ = test_stores
    draft_map = MapService.get_or_create_draft_map(db, str(store_a.id))

    node_1_id = str(uuid.uuid4())
    node_2_id = str(uuid.uuid4())
    edge_1_id = str(uuid.uuid4())

    nodes_payload = [
        {
            "id": node_1_id,
            "label": "Main Entrance QR",
            "x_coord": 0.0,
            "y_coord": 0.0,
            "node_type": MapNodeType.ENTRANCE_QR.value,
            "zone": "Entrance",
            "aisle": None,
        },
        {
            "id": node_2_id,
            "label": "Aisle 1 Junction",
            "x_coord": 10.0,
            "y_coord": 0.0,
            "node_type": MapNodeType.AISLE_JUNCTION.value,
            "zone": "Aisles",
            "aisle": "Aisle 1",
        },
    ]

    edges_payload = [
        {
            "id": edge_1_id,
            "from_node_id": node_1_id,
            "to_node_id": node_2_id,
            "distance_meters": 10.0,
            "weight": 1.0,
            "is_accessible": True,
            "is_blocked": False,
        }
    ]

    # 1. Batch creation
    result = MapService.save_elements_batch(
        db=db,
        store_id=str(store_a.id),
        map_id=str(draft_map.id),
        nodes=nodes_payload,
        edges=edges_payload,
    )

    assert result["status"] == "success"
    assert result["nodes_processed"] == 2
    assert result["edges_processed"] == 1

    # Verify elements in DB
    saved_node1 = db.query(MapNode).filter(MapNode.id == node_1_id).first()
    assert saved_node1 is not None
    assert saved_node1.label == "Main Entrance QR"

    saved_edge1 = db.query(MapEdge).filter(MapEdge.id == edge_1_id).first()
    assert saved_edge1 is not None
    assert saved_edge1.distance_meters == 10.0

    # 2. Batch update: Update node 2 label and mark edge 1 blocked
    update_nodes_payload = [
        {
            "id": node_2_id,
            "label": "Aisle 1 Junction - Updated",
            "x_coord": 12.0,
            "y_coord": 0.0,
        }
    ]
    update_edges_payload = [
        {
            "id": edge_1_id,
            "from_node_id": node_1_id,
            "to_node_id": node_2_id,
            "is_blocked": True,
        }
    ]
    update_result = MapService.save_elements_batch(
        db=db,
        store_id=str(store_a.id),
        map_id=str(draft_map.id),
        nodes=update_nodes_payload,
        edges=update_edges_payload,
    )
    assert update_result["status"] == "success"

    db.refresh(saved_node1)
    saved_node2 = db.query(MapNode).filter(MapNode.id == node_2_id).first()
    assert saved_node2.label == "Aisle 1 Junction - Updated"
    assert saved_node2.x_coord == 12.0

    db.refresh(saved_edge1)
    assert saved_edge1.is_blocked is True

    # 3. Batch deletion: Delete edge 1 and node 2
    delete_nodes = [{"id": node_2_id, "is_deleted": True}]
    delete_edges = [{"id": edge_1_id, "is_deleted": True}]
    del_result = MapService.save_elements_batch(
        db=db,
        store_id=str(store_a.id),
        map_id=str(draft_map.id),
        nodes=delete_nodes,
        edges=delete_edges,
    )
    assert del_result["status"] == "success"

    assert db.query(MapNode).filter(MapNode.id == node_2_id).first() is None
    assert db.query(MapEdge).filter(MapEdge.id == edge_1_id).first() is None


def test_save_elements_batch_store_mismatch(db: Session, test_stores):
    """Verifies HTTP 403 / Store Isolation error when attempting to update another store's map."""
    store_a, store_b = test_stores

    # Create map for Store A
    map_a = MapService.get_or_create_draft_map(db, str(store_a.id))

    # Attempt to update Store A's map using Store B's scoping context
    with pytest.raises(HTTPException) as exc_info:
        MapService.save_elements_batch(
            db=db,
            store_id=str(store_b.id),  # Mismatched store
            map_id=str(map_a.id),
            nodes=[{"label": "Hacker Node", "x_coord": 0.0, "y_coord": 0.0}],
            edges=[],
        )

    assert exc_info.value.status_code == 403
    assert "BR-14" in exc_info.value.detail or "isolation" in exc_info.value.detail.lower()


def test_publish_map_revision_success(db: Session, test_stores):
    """Verifies a valid draft map becomes is_active=True and previously active maps are set to is_active=False."""
    store_a, _ = test_stores

    # 1. Existing Active Map v1
    map_v1 = StoreMap(
        id=str(uuid.uuid4()),
        store_id=str(store_a.id),
        version=1,
        width_meters=50.0,
        height_meters=50.0,
        is_active=True,
    )
    db.add(map_v1)
    db.commit()

    # 2. Draft Map v2
    map_v2 = MapService.get_or_create_draft_map(db, str(store_a.id))
    assert map_v2.is_active is False
    assert map_v2.version == 2

    # Add valid graph elements (including ENTRANCE_QR)
    entrance_id = str(uuid.uuid4())
    shelf_id = str(uuid.uuid4())
    MapService.save_elements_batch(
        db=db,
        store_id=str(store_a.id),
        map_id=str(map_v2.id),
        nodes=[
            {
                "id": entrance_id,
                "label": "Main Entrance QR",
                "x_coord": 5.0,
                "y_coord": 5.0,
                "node_type": MapNodeType.ENTRANCE_QR.value,
            },
            {
                "id": shelf_id,
                "label": "Shelf A1",
                "x_coord": 15.0,
                "y_coord": 10.0,
                "node_type": MapNodeType.SHELF_TARGET.value,
            },
        ],
        edges=[
            {
                "from_node_id": entrance_id,
                "to_node_id": shelf_id,
                "distance_meters": 11.18,
            }
        ],
    )

    # 3. Publish draft v2
    published_map = MapService.publish_map_revision(db, str(store_a.id), str(map_v2.id))

    assert published_map.id == map_v2.id
    assert published_map.is_active is True

    # 4. Confirm previous map v1 is now deactivated
    db.refresh(map_v1)
    assert map_v1.is_active is False


def test_publish_map_revision_validation_failure(db: Session, test_stores):
    """Verifies attempting to publish a draft with validation errors raises 422 MapValidationError."""
    store_a, _ = test_stores
    draft_map = MapService.get_or_create_draft_map(db, str(store_a.id))

    # Add node without any ENTRANCE_QR node
    junction_id = str(uuid.uuid4())
    MapService.save_elements_batch(
        db=db,
        store_id=str(store_a.id),
        map_id=str(draft_map.id),
        nodes=[
            {
                "id": junction_id,
                "label": "Orphan Junction",
                "x_coord": 10.0,
                "y_coord": 10.0,
                "node_type": MapNodeType.AISLE_JUNCTION.value,
            }
        ],
        edges=[],
    )

    # Attempt to publish invalid draft (missing ENTRANCE_QR)
    with pytest.raises(MapValidationError) as exc_info:
        MapService.publish_map_revision(db, str(store_a.id), str(draft_map.id))

    assert exc_info.value.status_code == 422
    assert any("ENTRANCE_QR" in err for err in exc_info.value.errors)

    # Confirm map remains inactive draft
    db.refresh(draft_map)
    assert draft_map.is_active is False


def test_publish_map_revision_store_mismatch(db: Session, test_stores):
    """Verifies attempting to publish another store's map raises a store isolation error (HTTP 403)."""
    store_a, store_b = test_stores

    map_a = MapService.get_or_create_draft_map(db, str(store_a.id))

    # Attempt to publish Store A's map from Store B context
    with pytest.raises(HTTPException) as exc_info:
        MapService.publish_map_revision(db, str(store_b.id), str(map_a.id))

    assert exc_info.value.status_code == 403
    assert "BR-14" in exc_info.value.detail or "isolation" in exc_info.value.detail.lower()
