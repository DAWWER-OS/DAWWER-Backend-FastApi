import uuid
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.models.map_models import MapNodeType
from app.schemas import (
    MapEdgeBase,
    MapEdgeCreate,
    MapEdgeResponse,
    MapEdgeUpdate,
    MapNodeBase,
    MapNodeCreate,
    MapNodeResponse,
    MapNodeUpdate,
    NavigationRouteRequestSchema,
    NavigationRouteResponseSchema,
    NavigationStepSchema,
    StoreMapBase,
    StoreMapCreate,
    StoreMapResponse,
    StoreMapUpdate,
)


def test_map_node_schemas():
    # 1. MapNodeBase defaults
    node_base = MapNodeBase(
        label="Entrance Node",
        x_coord=12.5,
        y_coord=24.0,
    )
    assert node_base.node_type == MapNodeType.AISLE_JUNCTION.value
    assert node_base.label == "Entrance Node"
    assert node_base.x_coord == 12.5
    assert node_base.y_coord == 24.0
    assert node_base.zone is None
    assert node_base.aisle is None

    # 2. MapNodeCreate with custom enum
    node_create = MapNodeCreate(
        node_type=MapNodeType.ENTRANCE_QR,
        label="Main QR",
        x_coord=0.0,
        y_coord=0.0,
        zone="Entrance",
        aisle="Aisle 0",
    )
    assert node_create.node_type == MapNodeType.ENTRANCE_QR

    # 3. MapNodeUpdate partial
    node_update = MapNodeUpdate(label="Updated QR", is_active=False)
    assert node_update.label == "Updated QR"
    assert node_update.is_active is False
    assert node_update.x_coord is None

    # 4. MapNodeResponse serialization
    node_id = str(uuid.uuid4())
    map_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    node_resp = MapNodeResponse(
        id=node_id,
        map_id=map_id,
        node_type=MapNodeType.SHELF_TARGET.value,
        label="Target Shelf",
        x_coord=5.0,
        y_coord=10.0,
        is_active=True,
        created_at=now,
    )
    assert node_resp.id == node_id
    assert node_resp.map_id == map_id
    assert node_resp.is_active is True


def test_map_edge_schemas():
    from_id = str(uuid.uuid4())
    to_id = str(uuid.uuid4())

    # 1. Base edge validation
    edge_base = MapEdgeBase(
        from_node_id=from_id,
        to_node_id=to_id,
        distance_meters=15.2,
    )
    assert edge_base.weight == 1.0
    assert edge_base.is_accessible is True
    assert edge_base.is_blocked is False

    # Negative distance should fail
    with pytest.raises(ValidationError):
        MapEdgeBase(
            from_node_id=from_id,
            to_node_id=to_id,
            distance_meters=-1.0,
        )

    # 2. MapEdgeUpdate
    edge_update = MapEdgeUpdate(is_blocked=True, weight=2.5)
    assert edge_update.is_blocked is True
    assert edge_update.weight == 2.5
    assert edge_update.distance_meters is None

    # 3. MapEdgeResponse
    edge_id = str(uuid.uuid4())
    map_id = str(uuid.uuid4())
    edge_resp = MapEdgeResponse(
        id=edge_id,
        map_id=map_id,
        from_node_id=from_id,
        to_node_id=to_id,
        distance_meters=15.2,
        weight=1.0,
        is_accessible=True,
        is_blocked=False,
    )
    assert edge_resp.id == edge_id
    assert edge_resp.map_id == map_id


def test_store_map_schemas():
    # 1. Base defaults
    store_map_base = StoreMapBase()
    assert store_map_base.version == 1
    assert store_map_base.width_meters == 50.0
    assert store_map_base.height_meters == 50.0
    assert store_map_base.floor_plan_image_url is None

    # 2. StoreMapCreate
    map_create = StoreMapCreate(
        version=2,
        width_meters=100.0,
        height_meters=80.0,
        floor_plan_image_url="https://example.com/map.png",
    )
    assert map_create.version == 2
    assert map_create.width_meters == 100.0

    # 3. StoreMapResponse with nested nodes and edges
    map_id = str(uuid.uuid4())
    store_id = str(uuid.uuid4())
    node_id = str(uuid.uuid4())
    edge_id = str(uuid.uuid4())

    node_resp = MapNodeResponse(
        id=node_id,
        map_id=map_id,
        node_type="AISLE_JUNCTION",
        label="Junction 1",
        x_coord=10.0,
        y_coord=10.0,
    )
    edge_resp = MapEdgeResponse(
        id=edge_id,
        map_id=map_id,
        from_node_id=node_id,
        to_node_id=node_id,
        distance_meters=0.0,
    )

    map_resp = StoreMapResponse(
        id=map_id,
        store_id=store_id,
        version=1,
        width_meters=50.0,
        height_meters=50.0,
        is_active=True,
        nodes=[node_resp],
        edges=[edge_resp],
    )
    assert map_resp.id == map_id
    assert map_resp.store_id == store_id
    assert len(map_resp.nodes) == 1
    assert len(map_resp.edges) == 1
    assert map_resp.nodes[0].label == "Junction 1"


def test_navigation_route_schemas():
    # 1. NavigationRouteRequestSchema
    req = NavigationRouteRequestSchema(
        start_qr_code="QR-ENTRANCE-MAIN",
        target_product_ids=["prod-123", "prod-456"],
        avoid_crowded_edges=True,
    )
    assert req.start_qr_code == "QR-ENTRANCE-MAIN"
    assert req.target_product_ids == ["prod-123", "prod-456"]
    assert req.target_node_id is None
    assert req.avoid_crowded_edges is True

    # 2. NavigationStepSchema
    step = NavigationStepSchema(
        step_number=1,
        instruction="Proceed 10.0m forward to Aisle Junction 1",
        distance_meters=10.0,
        current_node_id="node-1",
        x_coord=0.0,
        y_coord=0.0,
    )
    assert step.step_number == 1
    assert step.distance_meters == 10.0

    # 3. NavigationRouteResponseSchema
    resp = NavigationRouteResponseSchema(
        store_id="store-123",
        total_distance_meters=45.5,
        estimated_time_seconds=36,
        ordered_product_stops=["prod-123", "prod-456"],
        path_nodes=[],
        steps=[step],
    )
    assert resp.store_id == "store-123"
    assert resp.total_distance_meters == 45.5
    assert resp.estimated_time_seconds == 36
    assert len(resp.steps) == 1
    assert resp.steps[0].instruction == "Proceed 10.0m forward to Aisle Junction 1"
