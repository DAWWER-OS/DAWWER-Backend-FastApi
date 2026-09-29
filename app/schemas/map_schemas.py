from datetime import datetime
from typing import List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

from app.models.map_models import MapNodeType


# ============================================================================
# MapNode / Element Schemas
# ============================================================================

class MapNodeBase(BaseModel):
    node_type: Union[MapNodeType, str] = Field(
        default=MapNodeType.AISLE_JUNCTION.value,
        description="Type of map node (ENTRANCE_QR, AISLE_JUNCTION, SHELF_TARGET, etc.)",
    )
    label: str = Field(..., min_length=1, description="Descriptive label for the node")
    x_coord: float = Field(..., description="Spatial X coordinate in meters on map")
    y_coord: float = Field(..., description="Spatial Y coordinate in meters on map")
    zone: Optional[str] = Field(default=None, description="Optional store zone or section")
    aisle: Optional[str] = Field(default=None, description="Optional aisle identifier")


class MapNodeCreate(MapNodeBase):
    pass


class MapNodeUpdate(BaseModel):
    node_type: Optional[Union[MapNodeType, str]] = None
    label: Optional[str] = None
    x_coord: Optional[float] = None
    y_coord: Optional[float] = None
    zone: Optional[str] = None
    aisle: Optional[str] = None
    is_active: Optional[bool] = None


class MapNodeResponse(MapNodeBase):
    id: str
    map_id: str
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MapElementCreateSchema(BaseModel):
    id: Optional[str] = Field(default=None, description="Optional UUID for the element")
    node_type: Union[MapNodeType, str] = Field(
        default=MapNodeType.SHELF_TARGET.value,
        description="Type of element (shelf, wall, entrance, fridge, etc.)",
    )
    label: str = Field(..., min_length=1, description="Label for the map element")
    x_coord: float = Field(..., description="X coordinate in meters")
    y_coord: float = Field(..., description="Y coordinate in meters")
    width: Optional[float] = Field(default=None, description="Spatial width dimension in meters")
    height: Optional[float] = Field(default=None, description="Spatial height dimension in meters")
    zone: Optional[str] = Field(default=None, description="Store zone or section")
    aisle: Optional[str] = Field(default=None, description="Aisle identifier")
    is_active: bool = Field(default=True, description="Active status")


class MapElementUpdateSchema(BaseModel):
    node_type: Optional[Union[MapNodeType, str]] = None
    label: Optional[str] = None
    x_coord: Optional[float] = None
    y_coord: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    zone: Optional[str] = None
    aisle: Optional[str] = None
    is_active: Optional[bool] = None


# ============================================================================
# Shelf Layout & Access Point Schemas (Task 7.2)
# ============================================================================

class AccessPointSchema(BaseModel):
    side: str = Field(default="Side A", description="Shelf side identifier (Side A / Side B)")
    label: str = Field(..., description="Access point label")
    x_coord: float = Field(..., description="Access point X coordinate for pathfinding snapping")
    y_coord: float = Field(..., description="Access point Y coordinate for pathfinding snapping")


class ShelfLayoutResponseSchema(BaseModel):
    shelf_id: str
    map_id: str
    store_id: Optional[str] = None
    label: str
    x_coord: float
    y_coord: float
    sides: int = Field(default=2, ge=1, le=2, description="Number of accessible shelf sides (1 or 2)")
    sections_count: int = Field(default=4, ge=1, description="Total vertical sections/bays")
    levels_count: int = Field(default=5, ge=1, description="Total horizontal shelf levels")
    zone: Optional[str] = None
    aisle: Optional[str] = None
    access_points: List[AccessPointSchema] = Field(default_factory=list, description="Navigation snapping access points")

    model_config = ConfigDict(from_attributes=True)


class ShelfLayoutUpdateSchema(BaseModel):
    sides: Optional[int] = Field(default=None, ge=1, le=2, description="Number of accessible shelf sides (1 or 2)")
    sections_count: Optional[int] = Field(default=None, ge=1, description="Total vertical sections/bays")
    levels_count: Optional[int] = Field(default=None, ge=1, description="Total horizontal shelf levels")
    x_coord: Optional[float] = Field(default=None, description="Updated shelf X coordinate")
    y_coord: Optional[float] = Field(default=None, description="Updated shelf Y coordinate")
    label: Optional[str] = Field(default=None, description="Updated shelf label")
    zone: Optional[str] = None
    aisle: Optional[str] = None
    access_points: Optional[List[AccessPointSchema]] = Field(default=None, description="Custom access points")


# ============================================================================
# MapEdge Schemas
# ============================================================================

class MapEdgeBase(BaseModel):
    from_node_id: str = Field(..., description="UUID of source map node")
    to_node_id: str = Field(..., description="UUID of destination map node")
    distance_meters: float = Field(..., ge=0.0, description="Physical distance in meters")
    weight: float = Field(default=1.0, ge=0.0, description="Dynamic traversal weight/cost")
    is_accessible: bool = Field(default=True, description="Accessible for trolleys/wheelchairs")
    is_blocked: bool = Field(default=False, description="Temporarily blocked or obstructed")


class MapEdgeCreate(MapEdgeBase):
    pass


class MapEdgeUpdate(BaseModel):
    from_node_id: Optional[str] = None
    to_node_id: Optional[str] = None
    distance_meters: Optional[float] = Field(default=None, ge=0.0)
    weight: Optional[float] = Field(default=None, ge=0.0)
    is_accessible: Optional[bool] = None
    is_blocked: Optional[bool] = None


class MapEdgeResponse(MapEdgeBase):
    id: str
    map_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# StoreMap Schemas
# ============================================================================

class StoreMapBase(BaseModel):
    version: int = Field(default=1, ge=1, description="Floor plan revision/version number")
    floor_plan_image_url: Optional[str] = Field(default=None, description="URL of floor plan image")
    width_meters: float = Field(default=50.0, gt=0.0, description="Total store map width in meters")
    height_meters: float = Field(default=50.0, gt=0.0, description="Total store map height in meters")


class StoreMapCreate(StoreMapBase):
    pass


class StoreMapUpdate(BaseModel):
    version: Optional[int] = Field(default=None, ge=1)
    floor_plan_image_url: Optional[str] = None
    width_meters: Optional[float] = Field(default=None, gt=0.0)
    height_meters: Optional[float] = Field(default=None, gt=0.0)
    is_active: Optional[bool] = None


class StoreMapResponse(StoreMapBase):
    id: str
    store_id: str
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    nodes: List[MapNodeResponse] = Field(default_factory=list)
    edges: List[MapEdgeResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Navigation Request & Response Schemas
# ============================================================================

class NavigationRouteRequestSchema(BaseModel):
    start_node_id: Optional[str] = Field(default=None, description="Starting node UUID")
    start_qr_code: Optional[str] = Field(default=None, description="Scanned QR code label/identifier at entrance or checkpoint")
    target_product_ids: Optional[List[str]] = Field(default=None, description="List of target product IDs to navigate to")
    target_node_id: Optional[str] = Field(default=None, description="Explicit target destination node UUID")
    avoid_crowded_edges: bool = Field(default=True, description="Whether to apply edge weighting to avoid crowded aisles")


class NavigationStepSchema(BaseModel):
    step_number: int = Field(..., description="Sequential turn-by-turn step index")
    instruction: str = Field(..., description="Human-readable navigation instruction")
    distance_meters: float = Field(..., description="Distance for this step in meters")
    current_node_id: str = Field(..., description="Node UUID at which this step begins")
    x_coord: float = Field(..., description="X coordinate of current step node")
    y_coord: float = Field(..., description="Y coordinate of current step node")

    model_config = ConfigDict(from_attributes=True)


class NavigationRouteResponseSchema(BaseModel):
    store_id: str
    total_distance_meters: float = Field(..., description="Total route distance in meters")
    estimated_time_seconds: int = Field(..., description="Estimated walking time in seconds")
    ordered_product_stops: List[str] = Field(default_factory=list, description="Ordered product stop IDs along optimal route")
    path_nodes: List[MapNodeResponse] = Field(default_factory=list, description="Full sequence of nodes visited along the path")
    steps: List[NavigationStepSchema] = Field(default_factory=list, description="Turn-by-turn guidance steps")

    model_config = ConfigDict(from_attributes=True)


# Type Aliases for consistency with other schema conventions
MapNodeSchema = MapNodeResponse
MapEdgeSchema = MapEdgeResponse
StoreMapSchema = StoreMapResponse


# ============================================================================
# Product Placement & Spatial Location Schemas (Task 7.3)
# ============================================================================

class ProductPlacementCreateSchema(BaseModel):
    product_id: str = Field(..., description="UUID or identifier of catalog product")
    store_id: Optional[str] = Field(default=None, description="Store UUID scope")
    shelf_id: str = Field(..., description="UUID of map node / shelf target")
    section: Optional[str] = Field(default="1", description="Section / bay / rack identifier")
    level: Optional[str] = Field(default="1", description="Shelf level identifier")
    zone: Optional[str] = Field(default=None, description="Store zone or section")
    aisle: Optional[str] = Field(default=None, description="Aisle identifier")
    map_target: Optional[str] = Field(default=None, description="Formatted location string override")
    is_active: bool = Field(default=True, description="Placement active status")


class ProductPlacementUpdateSchema(BaseModel):
    shelf_id: Optional[str] = Field(default=None, description="Updated map node / shelf target UUID")
    section: Optional[str] = Field(default=None, description="Updated section / rack")
    level: Optional[str] = Field(default=None, description="Updated shelf level")
    zone: Optional[str] = Field(default=None, description="Updated store zone")
    aisle: Optional[str] = Field(default=None, description="Updated aisle")
    map_target: Optional[str] = Field(default=None, description="Updated formatted location string")
    is_active: Optional[bool] = Field(default=None, description="Placement active status")


class ProductLocationResponseSchema(BaseModel):
    placement_id: str = Field(..., description="Product placement UUID")
    product_id: str = Field(..., description="Catalog product ID")
    store_id: str = Field(..., description="Store UUID")
    shelf_id: Optional[str] = Field(default=None, description="Attached map node / shelf ID")
    map_target_node_id: Optional[str] = Field(default=None, description="Attached map node / shelf ID")
    zone: Optional[str] = None
    aisle: Optional[str] = None
    section: Optional[str] = Field(default=None, description="Section / bay / rack")
    rack: Optional[str] = Field(default=None, description="Section / bay / rack")
    level: Optional[str] = Field(default=None, description="Shelf level")
    shelf: Optional[str] = Field(default=None, description="Shelf level")
    location_code: Optional[str] = Field(default=None, description="Formatted location string")
    map_target: Optional[str] = Field(default=None, description="Formatted location string")
    x_coord: Optional[float] = Field(default=None, description="Spatial X coordinate of shelf node")
    y_coord: Optional[float] = Field(default=None, description="Spatial Y coordinate of shelf node")
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ============================================================================
# Catalog Search & Floor Revision Schemas (Task 7.4)
# ============================================================================

class ProductCatalogSearchResponseSchema(BaseModel):
    id: str = Field(..., description="Product UUID")
    product_id: str = Field(..., description="Product UUID")
    store_id: str = Field(..., description="Store UUID")
    product_name: str = Field(..., description="Name of the product")
    category: str = Field(..., description="Category of the product")
    price: float = Field(..., description="Unit price")
    stock_status: str = Field(default="IN_STOCK", description="Inventory stock status")
    quantity: int = Field(default=0, description="Available stock quantity")
    zone: Optional[str] = Field(default=None, description="Store zone")
    aisle: Optional[str] = Field(default=None, description="Store aisle")
    rack: Optional[str] = Field(default=None, description="Store rack / section")
    shelf: Optional[str] = Field(default=None, description="Shelf level")
    map_target: Optional[str] = Field(default=None, description="Formatted map target location string")
    map_target_node_id: Optional[str] = Field(default=None, description="Attached map node ID")
    availableInStore: bool = Field(default=False, description="True if product is placed on active published floor map")
    available_in_store: bool = Field(default=False, description="True if product is placed on active published floor map")
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class FloorRevisionResponseSchema(BaseModel):
    id: str = Field(..., description="Floor map revision UUID")
    map_id: str = Field(..., description="Map UUID")
    store_id: str = Field(..., description="Store UUID")
    version: int = Field(..., description="Revision version number")
    is_active: bool = Field(..., description="Whether this revision is currently active")
    floor_plan_image_url: Optional[str] = Field(default=None, description="Floor plan image URL")
    width_meters: float = Field(default=50.0, description="Map width in meters")
    height_meters: float = Field(default=50.0, description="Map height in meters")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


