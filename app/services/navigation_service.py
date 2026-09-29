import heapq
import math
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models.map_models import MapEdge, MapNode, MapNodeType, StoreMap
from app.models.product import ProductLocation, StoreProduct
from app.schemas.map_schemas import (
    MapNodeResponse,
    NavigationRouteResponseSchema,
    NavigationStepSchema,
)

# ============================================================================
# Domain Constants
# ============================================================================

DEFAULT_GRID_RESOLUTION_CM = 20.0  # 20 cm per grid cell
DEFAULT_INFLATION_RADIUS_CM = 20.0  # 20 cm clearance inflation for obstacles
DEFAULT_WALKING_SPEED_MPS = 1.2    # ~1.2 meters per second walking speed
SQRT_2 = math.sqrt(2.0)


# ============================================================================
# Exceptions
# ============================================================================

class NavigationError(Exception):
    """Base exception for navigation operations."""
    pass


class UnreachableDestinationError(NavigationError):
    """Raised when A* search cannot find a valid path to the destination."""
    pass


class StoreMapNotFoundError(NavigationError):
    """Raised when no active map is found for the specified store."""
    pass


class LocationResolutionError(NavigationError):
    """Raised when start or destination location cannot be mapped to coordinates."""
    pass


# ============================================================================
# Spatial Grid Graph (20cm Rasterized Floor Model)
# ============================================================================

class WalkableGridGraph:
    """Represents a 2D rasterized floor navigation grid with 20cm node resolution.
    
    Origin is top-left (x increases right, y increases down).
    All internal distance calculations use centimeters (cm).
    """

    def __init__(
        self,
        width_meters: float = 50.0,
        height_meters: float = 50.0,
        resolution_cm: float = DEFAULT_GRID_RESOLUTION_CM,
    ):
        self.width_meters = float(width_meters)
        self.height_meters = float(height_meters)
        self.resolution_cm = float(resolution_cm)

        self.width_cm = self.width_meters * 100.0
        self.height_cm = self.height_meters * 100.0

        self.cols = max(1, int(math.ceil(self.width_cm / self.resolution_cm)))
        self.rows = max(1, int(math.ceil(self.height_cm / self.resolution_cm)))

        # 2D Grid: True = walkable, False = obstacle / inflated border
        self.walkable: List[List[bool]] = [
            [True for _ in range(self.cols)] for _ in range(self.rows)
        ]

        # Traversal weights: multiplier for crowding or terrain cost (default 1.0)
        self.weights: List[List[float]] = [
            [1.0 for _ in range(self.cols)] for _ in range(self.rows)
        ]

        # Registered named landmarks and obstacles
        self.obstacles: List[Dict[str, Any]] = []
        self.named_nodes: Dict[str, Dict[str, Any]] = {}

    def is_in_bounds(self, col: int, row: int) -> bool:
        return 0 <= col < self.cols and 0 <= row < self.rows

    def coords_to_grid(self, x_cm: float, y_cm: float) -> Tuple[int, int]:
        col = int(round(x_cm / self.resolution_cm))
        row = int(round(y_cm / self.resolution_cm))
        col = max(0, min(col, self.cols - 1))
        row = max(0, min(row, self.rows - 1))
        return col, row

    def grid_to_coords_cm(self, col: int, row: int) -> Tuple[float, float]:
        return col * self.resolution_cm, row * self.resolution_cm

    def grid_to_coords_meters(self, col: int, row: int) -> Tuple[float, float]:
        return (col * self.resolution_cm) / 100.0, (row * self.resolution_cm) / 100.0

    def add_obstacle(
        self,
        x_min_cm: float,
        y_min_cm: float,
        x_max_cm: float,
        y_max_cm: float,
        inflate_cm: float = DEFAULT_INFLATION_RADIUS_CM,
        obstacle_type: str = "shelf",
        access_point_cm: Optional[Tuple[float, float]] = None,
    ):
        """Rasterizes a solid obstacle into the grid and inflates its borders by 20cm."""
        self.obstacles.append({
            "x_min_cm": x_min_cm,
            "y_min_cm": y_min_cm,
            "x_max_cm": x_max_cm,
            "y_max_cm": y_max_cm,
            "type": obstacle_type,
            "access_point_cm": access_point_cm,
        })

        # Inflate borders by inflate_cm
        inf_x_min = max(0.0, x_min_cm - inflate_cm)
        inf_y_min = max(0.0, y_min_cm - inflate_cm)
        inf_x_max = min(self.width_cm, x_max_cm + inflate_cm)
        inf_y_max = min(self.height_cm, y_max_cm + inflate_cm)

        c_start, r_start = self.coords_to_grid(inf_x_min, inf_y_min)
        c_end, r_end = self.coords_to_grid(inf_x_max, inf_y_max)

        for r in range(r_start, min(r_end + 1, self.rows)):
            for c in range(c_start, min(c_end + 1, self.cols)):
                self.walkable[r][c] = False

    def set_cell_weight(self, col: int, row: int, weight: float):
        if self.is_in_bounds(col, row):
            self.weights[row][col] = max(0.1, float(weight))

    def get_nearest_walkable_cell(
        self,
        target_col: int,
        target_row: int,
        max_search_radius: int = 50,
    ) -> Optional[Tuple[int, int]]:
        """Finds the nearest walkable cell (shelf access point) using BFS if target is inside an obstacle."""
        if not self.is_in_bounds(target_col, target_row):
            return None

        if self.walkable[target_row][target_col]:
            return target_col, target_row

        queue = [(target_col, target_row)]
        visited = {(target_col, target_row)}

        directions = [
            (0, 1), (0, -1), (1, 0), (-1, 0),
            (1, 1), (1, -1), (-1, 1), (-1, -1),
        ]

        while queue:
            c, r = queue.pop(0)
            if self.walkable[r][c]:
                return c, r

            for dc, dr in directions:
                nc, nr = c + dc, r + dr
                if self.is_in_bounds(nc, nr) and (nc, nr) not in visited:
                    dist = math.hypot(nc - target_col, nr - target_row)
                    if dist <= max_search_radius:
                        visited.add((nc, nr))
                        queue.append((nc, nr))

        return None

    def get_neighbors(
        self,
        col: int,
        row: int,
        avoid_crowded: bool = True,
    ) -> List[Tuple[int, int, float]]:
        """Returns 8-directional walkable neighbors with diagonal corner-cutting prevention."""
        neighbors: List[Tuple[int, int, float]] = []

        # 4-orthogonal
        orthogonal = [
            (0, 1, self.resolution_cm),
            (0, -1, self.resolution_cm),
            (1, 0, self.resolution_cm),
            (-1, 0, self.resolution_cm),
        ]

        for dc, dr, dist in orthogonal:
            nc, nr = col + dc, row + dr
            if self.is_in_bounds(nc, nr) and self.walkable[nr][nc]:
                weight = self.weights[nr][nc] if avoid_crowded else 1.0
                neighbors.append((nc, nr, dist * weight))

        # 4-diagonal (only valid if both adjacent orthogonal cells are walkable)
        diagonal = [
            (1, 1, self.resolution_cm * SQRT_2),
            (1, -1, self.resolution_cm * SQRT_2),
            (-1, 1, self.resolution_cm * SQRT_2),
            (-1, -1, self.resolution_cm * SQRT_2),
        ]

        for dc, dr, dist in diagonal:
            nc, nr = col + dc, row + dr
            if (
                self.is_in_bounds(nc, nr)
                and self.walkable[nr][nc]
                and self.walkable[row][nc]
                and self.walkable[nr][col]
            ):
                weight = self.weights[nr][nc] if avoid_crowded else 1.0
                neighbors.append((nc, nr, dist * weight))

        return neighbors

    def has_line_of_sight(self, c1: int, r1: int, c2: int, r2: int) -> bool:
        """Bresenham-based raycaster checking line of sight across walkable cells."""
        dc = abs(c2 - c1)
        dr = abs(r2 - r1)
        c = c1
        r = r1
        step_c = 1 if c2 >= c1 else -1
        step_r = 1 if r2 >= r1 else -1

        if not self.walkable[r][c]:
            return False

        if dc > dr:
            err = 2 * dr - dc
            while c != c2:
                if not self.walkable[r][c]:
                    return False
                if err >= 0:
                    r += step_r
                    err -= 2 * dc
                c += step_c
                err += 2 * dr
        else:
            err = 2 * dc - dr
            while r != r2:
                if not self.walkable[r][c]:
                    return False
                if err >= 0:
                    c += step_c
                    err -= 2 * dr
                r += step_r
                err += 2 * dc

        return self.walkable[r2][c2]


# ============================================================================
# Navigation Service Engine
# ============================================================================

class NavigationService:
    """Core 2D Navigation Engine and A* Routing Service for DAWER Store Maps."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    def build_walkable_graph(
        self,
        map_model: StoreMap,
        obstacles: Optional[List[Dict[str, Any]]] = None,
        resolution_cm: float = DEFAULT_GRID_RESOLUTION_CM,
    ) -> WalkableGridGraph:
        """Rasterizes store floor elements, shelf obstacles, and blocked edges into a 20cm grid."""
        width_m = float(map_model.width_meters or 50.0)
        height_m = float(map_model.height_meters or 50.0)

        graph = WalkableGridGraph(
            width_meters=width_m,
            height_meters=height_m,
            resolution_cm=resolution_cm,
        )

        # 1. Register explicit map nodes
        if hasattr(map_model, "nodes") and map_model.nodes:
            for node in map_model.nodes:
                if getattr(node, "is_active", True):
                    x_cm = float(node.x_coord) * 100.0
                    y_cm = float(node.y_coord) * 100.0
                    graph.named_nodes[str(node.id)] = {
                        "id": str(node.id),
                        "label": node.label,
                        "node_type": node.node_type,
                        "x_cm": x_cm,
                        "y_cm": y_cm,
                        "x_meters": float(node.x_coord),
                        "y_meters": float(node.y_coord),
                        "zone": getattr(node, "zone", None),
                        "aisle": getattr(node, "aisle", None),
                    }
                    if node.label:
                        graph.named_nodes[node.label.strip().upper()] = graph.named_nodes[str(node.id)]

        # 2. Add custom or registered obstacles
        if obstacles:
            for obs in obstacles:
                x_min = obs.get("x_min_cm", obs.get("x_min", 0.0) * 100.0 if "x_min" in obs else 0.0)
                y_min = obs.get("y_min_cm", obs.get("y_min", 0.0) * 100.0 if "y_min" in obs else 0.0)
                x_max = obs.get("x_max_cm", obs.get("x_max", 0.0) * 100.0 if "x_max" in obs else 0.0)
                y_max = obs.get("y_max_cm", obs.get("y_max", 0.0) * 100.0 if "y_max" in obs else 0.0)
                inflate = obs.get("inflate_cm", DEFAULT_INFLATION_RADIUS_CM)
                graph.add_obstacle(
                    x_min_cm=x_min,
                    y_min_cm=y_min,
                    x_max_cm=x_max,
                    y_max_cm=y_max,
                    inflate_cm=inflate,
                    obstacle_type=obs.get("type", "shelf"),
                )

        # 3. Apply edge blocking / crowding weights
        if hasattr(map_model, "edges") and map_model.edges:
            for edge in map_model.edges:
                from_info = graph.named_nodes.get(str(edge.from_node_id))
                to_info = graph.named_nodes.get(str(edge.to_node_id))
                if from_info and to_info:
                    c1, r1 = graph.coords_to_grid(from_info["x_cm"], from_info["y_cm"])
                    c2, r2 = graph.coords_to_grid(to_info["x_cm"], to_info["y_cm"])
                    if getattr(edge, "is_blocked", False) or not getattr(edge, "is_accessible", True):
                        # Block ray
                        self._apply_segment_walkability(graph, c1, r1, c2, r2, walkable=False)
                    elif getattr(edge, "weight", 1.0) > 1.0:
                        self._apply_segment_weight(graph, c1, r1, c2, r2, weight=edge.weight)

        return graph

    def _apply_segment_walkability(
        self, graph: WalkableGridGraph, c1: int, r1: int, c2: int, r2: int, walkable: bool
    ):
        """Marks grid cells along an edge segment as walkable or blocked."""
        dc = abs(c2 - c1)
        dr = abs(r2 - r1)
        c, r = c1, r1
        step_c = 1 if c2 >= c1 else -1
        step_r = 1 if r2 >= r1 else -1

        if graph.is_in_bounds(c, r):
            graph.walkable[r][c] = walkable

        if dc > dr:
            err = 2 * dr - dc
            while c != c2:
                if graph.is_in_bounds(c, r):
                    graph.walkable[r][c] = walkable
                if err >= 0:
                    r += step_r
                    err -= 2 * dc
                c += step_c
                err += 2 * dr
        else:
            err = 2 * dc - dr
            while r != r2:
                if graph.is_in_bounds(c, r):
                    graph.walkable[r][c] = walkable
                if err >= 0:
                    c += step_c
                    err -= 2 * dr
                r += step_r
                err += 2 * dc

        if graph.is_in_bounds(c2, r2):
            graph.walkable[r2][c2] = walkable

    def _apply_segment_weight(
        self, graph: WalkableGridGraph, c1: int, r1: int, c2: int, r2: int, weight: float
    ):
        """Applies traversal weight along a corridor edge."""
        dc = abs(c2 - c1)
        dr = abs(r2 - r1)
        c, r = c1, r1
        step_c = 1 if c2 >= c1 else -1
        step_r = 1 if r2 >= r1 else -1

        if graph.is_in_bounds(c, r):
            graph.weights[r][c] = max(graph.weights[r][c], weight)

        if dc > dr:
            err = 2 * dr - dc
            while c != c2:
                if graph.is_in_bounds(c, r):
                    graph.weights[r][c] = max(graph.weights[r][c], weight)
                if err >= 0:
                    r += step_r
                    err -= 2 * dc
                c += step_c
                err += 2 * dr
        else:
            err = 2 * dc - dr
            while r != r2:
                if graph.is_in_bounds(c, r):
                    graph.weights[r][c] = max(graph.weights[r][c], weight)
                if err >= 0:
                    c += step_c
                    err -= 2 * dr
                r += step_r
                err += 2 * dc

        if graph.is_in_bounds(c2, r2):
            graph.weights[r2][c2] = max(graph.weights[r2][c2], weight)

    # ------------------------------------------------------------------------
    # Start & Destination Resolvers
    # ------------------------------------------------------------------------

    def resolve_start_coordinates(
        self,
        graph: WalkableGridGraph,
        start_spec: Dict[str, Any],
        map_model: Optional[StoreMap] = None,
    ) -> Tuple[float, float, str]:
        """Resolves entrance QR code, node ID, or coordinate dictionary to (x_cm, y_cm, label)."""
        # 1. QR Code match
        if "start_qr_code" in start_spec and start_spec["start_qr_code"]:
            qr_target = str(start_spec["start_qr_code"]).strip()
            # Direct match by upper label
            if qr_target.upper() in graph.named_nodes:
                node = graph.named_nodes[qr_target.upper()]
                return node["x_cm"], node["y_cm"], node["label"]

            # Substring or ENTRANCE_QR match
            if map_model and hasattr(map_model, "nodes"):
                for node in map_model.nodes:
                    if (
                        qr_target.lower() in node.label.lower()
                        or node.node_type == MapNodeType.ENTRANCE_QR.value
                    ):
                        return float(node.x_coord) * 100.0, float(node.y_coord) * 100.0, node.label

        # 2. Node ID match
        if "start_node_id" in start_spec and start_spec["start_node_id"]:
            node_id = str(start_spec["start_node_id"]).strip()
            if node_id in graph.named_nodes:
                node = graph.named_nodes[node_id]
                return node["x_cm"], node["y_cm"], node["label"]

        # 3. Direct coordinates (meters or cm)
        if "x_cm" in start_spec and "y_cm" in start_spec:
            return float(start_spec["x_cm"]), float(start_spec["y_cm"]), "Start Point"

        if "x" in start_spec and "y" in start_spec:
            return float(start_spec["x"]) * 100.0, float(start_spec["y"]) * 100.0, "Start Point"

        # 4. Fallback to first entrance node in map
        if map_model and hasattr(map_model, "nodes") and map_model.nodes:
            for node in map_model.nodes:
                if node.node_type == MapNodeType.ENTRANCE_QR.value:
                    return float(node.x_coord) * 100.0, float(node.y_coord) * 100.0, node.label
            first_node = map_model.nodes[0]
            return float(first_node.x_coord) * 100.0, float(first_node.y_coord) * 100.0, first_node.label

        # Default fallback
        return 0.0, 0.0, "Store Entrance"

    def resolve_destination_coordinates(
        self,
        graph: WalkableGridGraph,
        destination_spec: Dict[str, Any],
        map_model: Optional[StoreMap] = None,
        product_locations: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Tuple[float, float, str]:
        """Resolves target product, shelf access point, or target node ID to (x_cm, y_cm, label)."""
        # 1. Target Product ID resolution
        if "target_product_id" in destination_spec and destination_spec["target_product_id"]:
            prod_id = str(destination_spec["target_product_id"]).strip()

            # Check explicit in-memory product locations map if provided
            if product_locations and prod_id in product_locations:
                p_info = product_locations[prod_id]
                x_cm = p_info.get("x_cm", p_info.get("x", 0.0) * 100.0)
                y_cm = p_info.get("y_cm", p_info.get("y", 0.0) * 100.0)
                label = p_info.get("label", f"Product {prod_id}")
                return x_cm, y_cm, label

            # Check DB if session available
            if self.db:
                loc = (
                    self.db.query(ProductLocation)
                    .filter(ProductLocation.product_id == prod_id)
                    .first()
                )
                if loc and loc.map_target_node:
                    n = loc.map_target_node
                    return float(n.x_coord) * 100.0, float(n.y_coord) * 100.0, n.label

                prod = (
                    self.db.query(StoreProduct)
                    .filter(StoreProduct.id == prod_id)
                    .first()
                )
                if prod and prod.map_target_node:
                    n = prod.map_target_node
                    return float(n.x_coord) * 100.0, float(n.y_coord) * 100.0, n.label

        # 2. Target Node ID
        if "target_node_id" in destination_spec and destination_spec["target_node_id"]:
            node_id = str(destination_spec["target_node_id"]).strip()
            if node_id in graph.named_nodes:
                node = graph.named_nodes[node_id]
                return node["x_cm"], node["y_cm"], node["label"]

        # 3. Direct coordinates
        if "x_cm" in destination_spec and "y_cm" in destination_spec:
            return float(destination_spec["x_cm"]), float(destination_spec["y_cm"]), "Destination"

        if "x" in destination_spec and "y" in destination_spec:
            return float(destination_spec["x"]) * 100.0, float(destination_spec["y"]) * 100.0, "Destination"

        raise LocationResolutionError(f"Cannot resolve destination specification: {destination_spec}")

    # ------------------------------------------------------------------------
    # A* Algorithm & Path Smoothing
    # ------------------------------------------------------------------------

    def run_astar(
        self,
        graph: WalkableGridGraph,
        start_cm: Tuple[float, float],
        goal_cm: Tuple[float, float],
        avoid_crowded: bool = True,
    ) -> List[Tuple[int, int]]:
        """Executes A* search algorithm using Euclidean distance heuristic on the 20cm grid."""
        start_c, start_r = graph.coords_to_grid(start_cm[0], start_cm[1])
        goal_c, goal_r = graph.coords_to_grid(goal_cm[0], goal_cm[1])

        # Ensure start and goal are walkable (snap to shelf access point if within obstacle)
        start_cell = graph.get_nearest_walkable_cell(start_c, start_r)
        goal_cell = graph.get_nearest_walkable_cell(goal_c, goal_r)

        if not start_cell or not goal_cell:
            raise UnreachableDestinationError(
                f"No walkable access point near start {start_cm} or destination {goal_cm}."
            )

        start_c, start_r = start_cell
        goal_c, goal_r = goal_cell

        if (start_c, start_r) == (goal_c, goal_r):
            return [(start_c, start_r)]

        # Priority Queue entries: (f_score, tie_breaker, (col, row))
        counter = 0
        open_set: List[Tuple[float, int, Tuple[int, int]]] = []
        heapq.heappush(open_set, (0.0, counter, (start_c, start_r)))

        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        g_score: Dict[Tuple[int, int], float] = {(start_c, start_r): 0.0}

        def heuristic(c: int, r: int) -> float:
            return math.hypot(
                (c - goal_c) * graph.resolution_cm,
                (r - goal_r) * graph.resolution_cm,
            )

        f_score: Dict[Tuple[int, int], float] = {
            (start_c, start_r): heuristic(start_c, start_r)
        }

        closed_set: Set[Tuple[int, int]] = set()

        while open_set:
            current_f, _, current = heapq.heappop(open_set)

            if current == (goal_c, goal_r):
                # Reconstruct path
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                return path

            if current in closed_set:
                continue
            closed_set.add(current)

            curr_c, curr_r = current
            curr_g = g_score[current]

            for nc, nr, move_cost in graph.get_neighbors(curr_c, curr_r, avoid_crowded=avoid_crowded):
                neighbor = (nc, nr)
                if neighbor in closed_set:
                    continue

                tentative_g = curr_g + move_cost
                if tentative_g < g_score.get(neighbor, float("inf")):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f = tentative_g + heuristic(nc, nr)
                    f_score[neighbor] = f
                    counter += 1
                    heapq.heappush(open_set, (f, counter, neighbor))

        raise UnreachableDestinationError(
            f"No path found between ({start_c}, {start_r}) and ({goal_c}, {goal_r}). Obstacles block all routes."
        )

    def smooth_path(
        self,
        graph: WalkableGridGraph,
        grid_path: List[Tuple[int, int]],
    ) -> List[Tuple[int, int]]:
        """Applies Line-of-Sight path smoothing to remove redundant zigzag grid steps."""
        if len(grid_path) <= 2:
            return grid_path

        smoothed = [grid_path[0]]
        current_idx = 0

        while current_idx < len(grid_path) - 1:
            furthest_idx = current_idx + 1
            for next_idx in range(len(grid_path) - 1, current_idx, -1):
                c1, r1 = grid_path[current_idx]
                c2, r2 = grid_path[next_idx]
                if graph.has_line_of_sight(c1, r1, c2, r2):
                    furthest_idx = next_idx
                    break
            smoothed.append(grid_path[furthest_idx])
            current_idx = furthest_idx

        return smoothed

    # ------------------------------------------------------------------------
    # Turn-by-Turn Instruction Generator
    # ------------------------------------------------------------------------

    def generate_turn_instructions(
        self,
        graph: WalkableGridGraph,
        waypoints_meters: List[Tuple[float, float]],
        start_label: str,
        destination_label: str,
    ) -> List[NavigationStepSchema]:
        """Generates clear, human-readable turn-by-turn walking instructions."""
        if not waypoints_meters:
            return []

        if len(waypoints_meters) == 1:
            x, y = waypoints_meters[0]
            return [
                NavigationStepSchema(
                    step_number=1,
                    instruction=f"You are at your destination: {destination_label}",
                    distance_meters=0.0,
                    current_node_id="dest-0",
                    x_coord=x,
                    y_coord=y,
                )
            ]

        steps: List[NavigationStepSchema] = []
        step_number = 1

        for i in range(len(waypoints_meters) - 1):
            p1 = waypoints_meters[i]
            p2 = waypoints_meters[i + 1]
            dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])

            if i == 0:
                instruction = f"Start at {start_label}, proceed {dist:.1f}m forward"
            else:
                p0 = waypoints_meters[i - 1]
                # Angle calculation
                angle_prev = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
                angle_curr = math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))
                turn = (angle_curr - angle_prev + 180) % 360 - 180

                if -25 <= turn <= 25:
                    action = "Continue straight"
                elif 25 < turn <= 65:
                    action = "Bear slightly right"
                elif 65 < turn <= 120:
                    action = "Turn right"
                elif -65 <= turn < -25:
                    action = "Bear slightly left"
                elif -120 <= turn < -65:
                    action = "Turn left"
                else:
                    action = "Make a sharp turn"

                # Check if near a named waypoint
                nearby_name = None
                for node_info in graph.named_nodes.values():
                    ndist = math.hypot(p1[0] - node_info["x_meters"], p1[1] - node_info["y_meters"])
                    if ndist < 2.0 and node_info["label"] not in (start_label, destination_label):
                        nearby_name = node_info["label"]
                        break

                if nearby_name:
                    instruction = f"{action} at {nearby_name} and proceed {dist:.1f}m"
                else:
                    instruction = f"{action} and proceed {dist:.1f}m"

            steps.append(
                NavigationStepSchema(
                    step_number=step_number,
                    instruction=instruction,
                    distance_meters=round(dist, 2),
                    current_node_id=f"step-{step_number}",
                    x_coord=round(p1[0], 2),
                    y_coord=round(p1[1], 2),
                )
            )
            step_number += 1

        # Arrival final step
        final_x, final_y = waypoints_meters[-1]
        steps.append(
            NavigationStepSchema(
                step_number=step_number,
                instruction=f"Arrive at destination: {destination_label}",
                distance_meters=0.0,
                current_node_id=f"step-{step_number}",
                x_coord=round(final_x, 2),
                y_coord=round(final_y, 2),
            )
        )

        return steps

    # ------------------------------------------------------------------------
    # Public Core API Methods
    # ------------------------------------------------------------------------

    def calculate_shortest_path(
        self,
        store_id: str,
        start_spec: Dict[str, Any],
        destination_spec: Dict[str, Any],
        avoid_crowded: bool = True,
        map_model: Optional[StoreMap] = None,
        obstacles: Optional[List[Dict[str, Any]]] = None,
        product_locations: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Calculates smoothed shortest path, total distance, walking time, and turn-by-turn guidance."""
        # 1. Resolve StoreMap if not directly injected
        if not map_model:
            if not self.db:
                raise StoreMapNotFoundError(f"Database session not available to lookup store {store_id}.")
            map_model = (
                self.db.query(StoreMap)
                .filter(StoreMap.store_id == store_id, StoreMap.is_active.is_(True))
                .first()
            )
            if not map_model:
                raise StoreMapNotFoundError(f"Active StoreMap not found for store {store_id}.")

        # 2. Build 20cm walkable grid graph
        graph = self.build_walkable_graph(map_model, obstacles=obstacles)

        # 3. Resolve start & destination coordinates
        start_x_cm, start_y_cm, start_label = self.resolve_start_coordinates(
            graph, start_spec, map_model
        )
        dest_x_cm, dest_y_cm, dest_label = self.resolve_destination_coordinates(
            graph, destination_spec, map_model, product_locations=product_locations
        )

        # 4. Execute A* search
        raw_grid_path = self.run_astar(
            graph,
            start_cm=(start_x_cm, start_y_cm),
            goal_cm=(dest_x_cm, dest_y_cm),
            avoid_crowded=avoid_crowded,
        )

        # 5. Line-of-sight path smoothing
        smoothed_grid_path = self.smooth_path(graph, raw_grid_path)

        # 6. Convert path to metric coordinates and MapNodeResponse
        metric_waypoints: List[Tuple[float, float]] = [
            graph.grid_to_coords_meters(c, r) for c, r in smoothed_grid_path
        ]

        path_nodes: List[MapNodeResponse] = []
        total_distance = 0.0

        for i, (xm, ym) in enumerate(metric_waypoints):
            if i > 0:
                total_distance += math.hypot(
                    xm - metric_waypoints[i - 1][0],
                    ym - metric_waypoints[i - 1][1],
                )

            label = start_label if i == 0 else (dest_label if i == len(metric_waypoints) - 1 else f"Waypoint {i}")
            node_type = (
                MapNodeType.ENTRANCE_QR.value if i == 0 else
                (MapNodeType.SHELF_TARGET.value if i == len(metric_waypoints) - 1 else MapNodeType.AISLE_JUNCTION.value)
            )
            path_nodes.append(
                MapNodeResponse(
                    id=f"wp-{i}",
                    map_id=str(getattr(map_model, "id", "map-default")),
                    node_type=node_type,
                    label=label,
                    x_coord=round(xm, 2),
                    y_coord=round(ym, 2),
                    is_active=True,
                )
            )

        # 7. Walking time (1.2 m/s)
        estimated_time = max(1, int(round(total_distance / DEFAULT_WALKING_SPEED_MPS)))

        # 8. Turn-by-turn guidance
        steps = self.generate_turn_instructions(
            graph, metric_waypoints, start_label, dest_label
        )

        ordered_stops: List[str] = []
        if "target_product_id" in destination_spec:
            ordered_stops.append(str(destination_spec["target_product_id"]))

        return {
            "store_id": store_id,
            "total_distance_meters": round(total_distance, 2),
            "estimated_time_seconds": estimated_time,
            "ordered_product_stops": ordered_stops,
            "path_nodes": path_nodes,
            "steps": steps,
        }

    def optimize_multi_stop_route(
        self,
        store_id: str,
        start_spec: Dict[str, Any],
        product_ids: List[str],
        avoid_crowded: bool = True,
        map_model: Optional[StoreMap] = None,
        obstacles: Optional[List[Dict[str, Any]]] = None,
        product_locations: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Optimizes a multi-product shopping path using Nearest-Neighbor + 2-opt swap, ending at Cashier."""
        # 1. Resolve StoreMap
        if not map_model:
            if not self.db:
                raise StoreMapNotFoundError(f"Database session not available to lookup store {store_id}.")
            map_model = (
                self.db.query(StoreMap)
                .filter(StoreMap.store_id == store_id, StoreMap.is_active.is_(True))
                .first()
            )
            if not map_model:
                raise StoreMapNotFoundError(f"Active StoreMap not found for store {store_id}.")

        graph = self.build_walkable_graph(map_model, obstacles=obstacles)

        # 2. Resolve Start
        start_x_cm, start_y_cm, start_label = self.resolve_start_coordinates(
            graph, start_spec, map_model
        )
        start_pt = (start_x_cm, start_y_cm, start_label, "START")

        # 3. Resolve Products
        product_stops: List[Tuple[float, float, str, str]] = []
        for pid in product_ids:
            px, py, plabel = self.resolve_destination_coordinates(
                graph, {"target_product_id": pid}, map_model, product_locations=product_locations
            )
            product_stops.append((px, py, plabel, pid))

        # 4. Resolve Cashier / Checkout point
        cashier_pt = None
        if map_model and hasattr(map_model, "nodes"):
            for n in map_model.nodes:
                if n.node_type == MapNodeType.CASHIER.value:
                    cashier_pt = (float(n.x_coord) * 100.0, float(n.y_coord) * 100.0, n.label, "CASHIER")
                    break

        if not cashier_pt:
            # Fallback cashier near entrance or bottom-right
            cashier_pt = (start_x_cm + 500.0, start_y_cm, "Checkout Counter", "CASHIER")

        if not product_stops:
            # Direct route start to cashier
            return self.calculate_shortest_path(
                store_id=store_id,
                start_spec=start_spec,
                destination_spec={"x_cm": cashier_pt[0], "y_cm": cashier_pt[1]},
                avoid_crowded=avoid_crowded,
                map_model=map_model,
                obstacles=obstacles,
            )

        # 5. Nearest-Neighbor TSP heuristic
        unvisited = list(product_stops)
        ordered_stops: List[Tuple[float, float, str, str]] = []
        current = start_pt

        while unvisited:
            nearest_idx = 0
            best_dist = float("inf")
            for i, p in enumerate(unvisited):
                d = math.hypot(p[0] - current[0], p[1] - current[1])
                if d < best_dist:
                    best_dist = d
                    nearest_idx = i
            next_stop = unvisited.pop(nearest_idx)
            ordered_stops.append(next_stop)
            current = next_stop

        # 6. 2-opt swap refinement
        def route_distance(order: List[Tuple[float, float, str, str]]) -> float:
            full = [start_pt] + order + [cashier_pt]
            return sum(
                math.hypot(full[i + 1][0] - full[i][0], full[i + 1][1] - full[i][1])
                for i in range(len(full) - 1)
            )

        improved = True
        iterations = 0
        while improved and iterations < 50:
            improved = False
            iterations += 1
            for i in range(len(ordered_stops) - 1):
                for j in range(i + 1, len(ordered_stops)):
                    # Test reversal of segment [i:j+1]
                    new_order = (
                        ordered_stops[:i]
                        + ordered_stops[i : j + 1][::-1]
                        + ordered_stops[j + 1 :]
                    )
                    if route_distance(new_order) < route_distance(ordered_stops) - 1e-4:
                        ordered_stops = new_order
                        improved = True
                        break
                if improved:
                    break

        # 7. Concatenate shortest paths across all legs
        full_legs = [start_pt] + ordered_stops + [cashier_pt]
        all_metric_waypoints: List[Tuple[float, float]] = []
        total_distance = 0.0

        for i in range(len(full_legs) - 1):
            leg_start = full_legs[i]
            leg_end = full_legs[i + 1]

            leg_raw_path = self.run_astar(
                graph,
                start_cm=(leg_start[0], leg_start[1]),
                goal_cm=(leg_end[0], leg_end[1]),
                avoid_crowded=avoid_crowded,
            )
            leg_smoothed = self.smooth_path(graph, leg_raw_path)
            leg_metrics = [graph.grid_to_coords_meters(c, r) for c, r in leg_smoothed]

            if not all_metric_waypoints:
                all_metric_waypoints.extend(leg_metrics)
            else:
                all_metric_waypoints.extend(leg_metrics[1:])

        # Calculate final total distance
        for i in range(len(all_metric_waypoints) - 1):
            total_distance += math.hypot(
                all_metric_waypoints[i + 1][0] - all_metric_waypoints[i][0],
                all_metric_waypoints[i + 1][1] - all_metric_waypoints[i][1],
            )

        estimated_time = max(1, int(round(total_distance / DEFAULT_WALKING_SPEED_MPS)))

        # Build path nodes
        path_nodes: List[MapNodeResponse] = [
            MapNodeResponse(
                id=f"multi-wp-{i}",
                map_id=str(getattr(map_model, "id", "map-default")),
                node_type=MapNodeType.AISLE_JUNCTION.value,
                label=f"Waypoint {i}",
                x_coord=round(xm, 2),
                y_coord=round(ym, 2),
                is_active=True,
            )
            for i, (xm, ym) in enumerate(all_metric_waypoints)
        ]

        steps = self.generate_turn_instructions(
            graph, all_metric_waypoints, start_label, cashier_pt[2]
        )

        return {
            "store_id": store_id,
            "total_distance_meters": round(total_distance, 2),
            "estimated_time_seconds": estimated_time,
            "ordered_product_stops": [p[3] for p in ordered_stops],
            "path_nodes": path_nodes,
            "steps": steps,
        }
