import uuid
import pytest

from app.models.map_models import MapNode, MapNodeType, StoreMap
from app.services.navigation_service import (
    DEFAULT_INFLATION_RADIUS_CM,
    NavigationService,
    UnreachableDestinationError,
    WalkableGridGraph,
)


def create_dummy_map(width_m: float = 30.0, height_m: float = 30.0) -> StoreMap:
    store_map = StoreMap(
        id=str(uuid.uuid4()),
        store_id=str(uuid.uuid4()),
        version=1,
        width_meters=width_m,
        height_meters=height_m,
        is_active=True,
    )
    store_map.nodes = []
    store_map.edges = []
    return store_map


def test_astar_navigating_around_solid_wall_obstacle():
    """Test A* pathfinding navigating around a solid wall obstacle."""
    service = NavigationService()
    store_map = create_dummy_map(width_m=20.0, height_m=20.0)

    # Obstacle: Vertical wall from x=8m to 10m, extending from y=0m to 14m
    # Leaving an open passage from y=14.5m to 20.0m
    obstacles = [
        {
            "x_min_cm": 800.0,
            "y_min_cm": 0.0,
            "x_max_cm": 1000.0,
            "y_max_cm": 1400.0,
            "type": "wall",
            "inflate_cm": 20.0,
        }
    ]

    start_spec = {"x": 3.0, "y": 5.0}
    dest_spec = {"x": 15.0, "y": 5.0}

    result = service.calculate_shortest_path(
        store_id=str(store_map.store_id),
        start_spec=start_spec,
        destination_spec=dest_spec,
        map_model=store_map,
        obstacles=obstacles,
    )

    assert result is not None
    assert "total_distance_meters" in result
    assert "steps" in result
    assert len(result["steps"]) > 1

    # Direct line is 12m; with the wall detour down past y=14m, path should be > 20m
    assert result["total_distance_meters"] > 18.0
    assert result["estimated_time_seconds"] > 10

    # Ensure no path point penetrates the wall interior
    for node in result["path_nodes"]:
        x_cm = node.x_coord * 100.0
        y_cm = node.y_coord * 100.0
        if 800.0 <= x_cm <= 1000.0:
            assert y_cm > 1400.0, f"Path penetrated wall at ({node.x_coord}, {node.y_coord})"


def test_entrance_qr_resolution_to_start_coordinate():
    """Test entrance QR resolution to map start coordinate."""
    service = NavigationService()
    store_map = create_dummy_map(width_m=40.0, height_m=40.0)

    qr_node = MapNode(
        id=str(uuid.uuid4()),
        map_id=str(store_map.id),
        node_type=MapNodeType.ENTRANCE_QR.value,
        label="QR-ENTRANCE-MAIN",
        x_coord=2.4,
        y_coord=4.8,
        is_active=True,
    )
    dest_node = MapNode(
        id=str(uuid.uuid4()),
        map_id=str(store_map.id),
        node_type=MapNodeType.SHELF_TARGET.value,
        label="Shelf 1",
        x_coord=12.0,
        y_coord=15.0,
        is_active=True,
    )
    store_map.nodes = [qr_node, dest_node]

    # Test QR resolution with exact and lowercase inputs
    start_spec = {"start_qr_code": "qr-entrance-main"}
    dest_spec = {"target_node_id": str(dest_node.id)}

    result = service.calculate_shortest_path(
        store_id=str(store_map.store_id),
        start_spec=start_spec,
        destination_spec=dest_spec,
        map_model=store_map,
    )

    first_node = result["path_nodes"][0]
    assert abs(first_node.x_coord - 2.4) <= 0.2
    assert abs(first_node.y_coord - 4.8) <= 0.2
    assert first_node.label == "QR-ENTRANCE-MAIN"


def test_multi_stop_route_optimization_order():
    """Test multi-stop route optimization order logic (Nearest-Neighbor + 2-opt)."""
    service = NavigationService()
    store_map = create_dummy_map(width_m=60.0, height_m=20.0)

    entrance = MapNode(
        id=str(uuid.uuid4()),
        map_id=str(store_map.id),
        node_type=MapNodeType.ENTRANCE_QR.value,
        label="Main Entrance",
        x_coord=0.0,
        y_coord=5.0,
    )
    cashier = MapNode(
        id=str(uuid.uuid4()),
        map_id=str(store_map.id),
        node_type=MapNodeType.CASHIER.value,
        label="Checkout Cashier",
        x_coord=50.0,
        y_coord=5.0,
    )
    store_map.nodes = [entrance, cashier]

    # 3 products placed along the path:
    # Prod A at x=10m, Prod C at x=25m, Prod B at x=40m
    product_locations = {
        "prod_b": {"x": 40.0, "y": 5.0, "label": "Product B"},
        "prod_a": {"x": 10.0, "y": 5.0, "label": "Product A"},
        "prod_c": {"x": 25.0, "y": 5.0, "label": "Product C"},
    }

    # Pass in scrambled order [B, A, C]
    scrambled_ids = ["prod_b", "prod_a", "prod_c"]
    result = service.optimize_multi_stop_route(
        store_id=str(store_map.store_id),
        start_spec={"start_qr_code": "Main Entrance"},
        product_ids=scrambled_ids,
        map_model=store_map,
        product_locations=product_locations,
    )

    # Optimal sequence from Entrance (0m) to Cashier (50m) must be: prod_a -> prod_c -> prod_b
    assert result["ordered_product_stops"] == ["prod_a", "prod_c", "prod_b"]
    assert result["total_distance_meters"] > 0
    assert len(result["steps"]) > 0


def test_handling_isolated_unreachable_target_node():
    """Test handling of isolated/unreachable target nodes."""
    service = NavigationService()
    store_map = create_dummy_map(width_m=25.0, height_m=25.0)

    # Completely enclose destination (15m, 15m) inside solid boundary box [12m..18m] x [12m..18m]
    # with thick wall borders and no entrance
    obstacles = [
        # Top wall
        {"x_min_cm": 1200.0, "y_min_cm": 1200.0, "x_max_cm": 1800.0, "y_max_cm": 1300.0, "type": "wall"},
        # Bottom wall
        {"x_min_cm": 1200.0, "y_min_cm": 1700.0, "x_max_cm": 1800.0, "y_max_cm": 1800.0, "type": "wall"},
        # Left wall
        {"x_min_cm": 1200.0, "y_min_cm": 1200.0, "x_max_cm": 1300.0, "y_max_cm": 1800.0, "type": "wall"},
        # Right wall
        {"x_min_cm": 1700.0, "y_min_cm": 1200.0, "x_max_cm": 1800.0, "y_max_cm": 1800.0, "type": "wall"},
    ]

    start_spec = {"x": 2.0, "y": 2.0}
    dest_spec = {"x": 15.0, "y": 15.0}

    with pytest.raises(UnreachableDestinationError):
        service.calculate_shortest_path(
            store_id=str(store_map.store_id),
            start_spec=start_spec,
            destination_spec=dest_spec,
            map_model=store_map,
            obstacles=obstacles,
        )


def test_shelf_target_access_point_snapping():
    """Test that destination target inside an obstacle ends at an adjacent walkable access point."""
    graph = WalkableGridGraph(width_meters=10.0, height_meters=10.0)
    # Shelf at [200cm..400cm] x [200cm..600cm]
    graph.add_obstacle(
        x_min_cm=200.0,
        y_min_cm=200.0,
        x_max_cm=400.0,
        y_max_cm=600.0,
        inflate_cm=20.0,
        obstacle_type="shelf",
    )

    # Query target cell inside the shelf [300cm, 400cm]
    target_c, target_r = graph.coords_to_grid(300.0, 400.0)
    assert not graph.walkable[target_r][target_c], "Center of shelf should be unwalkable"

    access_cell = graph.get_nearest_walkable_cell(target_c, target_r)
    assert access_cell is not None
    ac, ar = access_cell
    assert graph.walkable[ar][ac], "Access point must be walkable"
