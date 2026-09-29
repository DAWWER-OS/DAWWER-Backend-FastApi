from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, verify_store_access
from app.models.map_models import StoreMap
from app.schemas.map_schemas import (
    FloorRevisionResponseSchema,
    MapElementCreateSchema,
    MapElementUpdateSchema,
    MapNodeResponse,
    ProductCatalogSearchResponseSchema,
    ProductLocationResponseSchema,
    ProductPlacementCreateSchema,
    ProductPlacementUpdateSchema,
    ShelfLayoutResponseSchema,
    ShelfLayoutUpdateSchema,
    StoreMapResponse,
)
from app.services.map_service import MapService, MapValidationError

router = APIRouter(tags=["Store Maps & Grid Management"])


class BatchElementsSchema(BaseModel):
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []


@router.get(
    "/api/v1/stores/{store_id}/maps/active",
    response_model=StoreMapResponse,
    status_code=status.HTTP_200_OK,
    summary="Get active published StoreMap",
)
def get_active_map(
    store_id: str,
    db: Session = Depends(get_db),
) -> StoreMapResponse:
    active_map = (
        db.query(StoreMap)
        .filter(StoreMap.store_id == store_id, StoreMap.is_active.is_(True))
        .first()
    )
    if not active_map:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active StoreMap not found for store '{store_id}'",
        )
    return StoreMapResponse.model_validate(active_map)


@router.get(
    "/api/v1/stores/{store_id}/maps/draft",
    response_model=StoreMapResponse,
    status_code=status.HTTP_200_OK,
    summary="Get or create draft StoreMap revision",
)
def get_or_create_draft_map(
    store_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> StoreMapResponse:
    draft = MapService.get_or_create_draft_map(db=db, store_id=store_id)
    return StoreMapResponse.model_validate(draft)


@router.post(
    "/api/v1/stores/{store_id}/maps/{map_id}/elements/batch",
    status_code=status.HTTP_200_OK,
    summary="Batch save map nodes and edges",
)
def save_elements_batch(
    store_id: str,
    map_id: str,
    payload: BatchElementsSchema,
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> Dict[str, Any]:
    return MapService.save_elements_batch(
        db=db,
        store_id=store_id,
        map_id=map_id,
        nodes=payload.nodes,
        edges=payload.edges,
    )


@router.post(
    "/api/v1/stores/{store_id}/maps/{map_id}/validate",
    status_code=status.HTTP_200_OK,
    summary="Validate map graph structure",
)
def validate_map_graph(
    store_id: str,
    map_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> Dict[str, Any]:
    return MapService.validate_map_graph(db=db, store_id=store_id, map_id=map_id)


@router.post(
    "/api/v1/stores/{store_id}/maps/{map_id}/publish",
    response_model=StoreMapResponse,
    status_code=status.HTTP_200_OK,
    summary="Publish map revision",
)
def publish_map_revision(
    store_id: str,
    map_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> StoreMapResponse:
    published = MapService.publish_map_revision(db=db, store_id=store_id, map_id=map_id)
    return StoreMapResponse.model_validate(published)


# ============================================================================
# Single Map Element CRUD Endpoints (Task 7.1)
# ============================================================================

@router.post(
    "/api/v1/floors/{floor_id}/elements",
    response_model=MapNodeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create single map element",
)
@router.post(
    "/api/v1/stores/{store_id}/floors/{floor_id}/elements",
    response_model=MapNodeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create single map element under store scoping",
)
def create_map_element_endpoint(
    floor_id: str,
    payload: MapElementCreateSchema,
    store_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> MapNodeResponse:
    element_data = payload.model_dump()
    new_node = MapService.create_map_element(
        db=db,
        floor_id=floor_id,
        element_data=element_data,
        store_id=store_id,
    )
    return MapNodeResponse.model_validate(new_node)


@router.patch(
    "/api/v1/elements/{element_id}",
    response_model=MapNodeResponse,
    status_code=status.HTTP_200_OK,
    summary="Partially update single map element",
)
@router.patch(
    "/api/v1/stores/{store_id}/elements/{element_id}",
    response_model=MapNodeResponse,
    status_code=status.HTTP_200_OK,
    summary="Partially update single map element under store scoping",
)
def update_map_element_endpoint(
    element_id: str,
    payload: MapElementUpdateSchema,
    store_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> MapNodeResponse:
    update_data = payload.model_dump(exclude_unset=True)
    updated_node = MapService.update_map_element(
        db=db,
        element_id=element_id,
        update_data=update_data,
        store_id=store_id,
    )
    return MapNodeResponse.model_validate(updated_node)


@router.delete(
    "/api/v1/elements/{element_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete single map element with safety constraints",
)
@router.delete(
    "/api/v1/stores/{store_id}/elements/{element_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete single map element with safety constraints under store scoping",
)
def delete_map_element_endpoint(
    element_id: str,
    store_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return MapService.delete_map_element(
        db=db,
        element_id=element_id,
        store_id=store_id,
    )


# ============================================================================
# Shelf Layout & Access Point Endpoints (Task 7.2)
# ============================================================================

@router.get(
    "/api/v1/shelves/{shelf_id}/layout",
    response_model=ShelfLayoutResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get shelf layout configuration and access points",
)
@router.get(
    "/api/v1/stores/{store_id}/shelves/{shelf_id}/layout",
    response_model=ShelfLayoutResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get shelf layout configuration under store scoping",
)
def get_shelf_layout_endpoint(
    shelf_id: str,
    store_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> ShelfLayoutResponseSchema:
    layout_dict = MapService.get_shelf_layout(
        db=db,
        shelf_id=shelf_id,
        store_id=store_id,
    )
    return ShelfLayoutResponseSchema(**layout_dict)


@router.patch(
    "/api/v1/shelves/{shelf_id}/layout",
    response_model=ShelfLayoutResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Update shelf layout physical parameters and access points",
)
@router.patch(
    "/api/v1/stores/{store_id}/shelves/{shelf_id}/layout",
    response_model=ShelfLayoutResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Update shelf layout physical parameters under store scoping",
)
def update_shelf_layout_endpoint(
    shelf_id: str,
    payload: ShelfLayoutUpdateSchema,
    store_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> ShelfLayoutResponseSchema:
    layout_data = payload.model_dump(exclude_unset=True)
    updated_layout = MapService.update_shelf_layout(
        db=db,
        shelf_id=shelf_id,
        layout_data=layout_data,
        store_id=store_id,
    )
    return ShelfLayoutResponseSchema(**updated_layout)


# ============================================================================
# Product Placement & Spatial Location Mapping Endpoints (Task 7.3)
# ============================================================================

@router.post(
    "/api/v1/placements",
    response_model=ProductLocationResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create product placement mapping product to map shelf node",
)
@router.post(
    "/api/v1/stores/{store_id}/placements",
    response_model=ProductLocationResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create product placement mapping under store scoping",
)
def create_product_placement_endpoint(
    payload: ProductPlacementCreateSchema,
    store_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> ProductLocationResponseSchema:
    effective_store_id = store_id or payload.store_id
    if not effective_store_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="store_id is required for product placement creation",
        )
    placement_dict = MapService.create_product_placement(
        db=db,
        store_id=effective_store_id,
        placement_data=payload.model_dump(),
    )
    return ProductLocationResponseSchema(**placement_dict)


@router.patch(
    "/api/v1/placements/{placement_id}",
    response_model=ProductLocationResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Update product shelf placement location",
)
@router.patch(
    "/api/v1/stores/{store_id}/placements/{placement_id}",
    response_model=ProductLocationResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Update product shelf placement location under store scoping",
)
def update_product_placement_endpoint(
    placement_id: str,
    payload: ProductPlacementUpdateSchema,
    store_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> ProductLocationResponseSchema:
    updated_dict = MapService.update_product_placement(
        db=db,
        placement_id=placement_id,
        update_data=payload.model_dump(exclude_unset=True),
        store_id=store_id,
    )
    return ProductLocationResponseSchema(**updated_dict)


@router.delete(
    "/api/v1/placements/{placement_id}",
    status_code=status.HTTP_200_OK,
    summary="Unlink product placement from map shelf node",
)
@router.delete(
    "/api/v1/stores/{store_id}/placements/{placement_id}",
    status_code=status.HTTP_200_OK,
    summary="Unlink product placement from map shelf node under store scoping",
)
def delete_product_placement_endpoint(
    placement_id: str,
    store_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return MapService.delete_product_placement(
        db=db,
        placement_id=placement_id,
        store_id=store_id,
    )


@router.get(
    "/api/v1/stores/{store_id}/products/{product_id}/locations",
    response_model=List[ProductLocationResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="Get physical floor locations and map coordinates for product",
)
def get_product_locations_endpoint(
    store_id: str,
    product_id: str,
    db: Session = Depends(get_db),
) -> List[ProductLocationResponseSchema]:
    locations = MapService.get_product_locations(
        db=db,
        store_id=store_id,
        product_id=product_id,
    )
    return [ProductLocationResponseSchema(**loc) for loc in locations]


# ============================================================================
# Catalog Search with Map Placement Status & Floor Revisions (Task 7.4)
# ============================================================================

@router.get(
    "/api/v1/products",
    response_model=List[ProductCatalogSearchResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="Search store catalog products with map placement status",
)
def search_products_with_map_status_endpoint(
    store_id: Optional[str] = Query(None, alias="storeId"),
    store_id_param: Optional[str] = Query(None, alias="store_id"),
    search: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> List[ProductCatalogSearchResponseSchema]:
    eff_store_id = store_id or store_id_param
    if not eff_store_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="storeId query parameter is required for catalog product search",
        )
    query_text = search or query or ""
    results = MapService.search_store_catalog_with_map(
        db=db,
        store_id=eff_store_id,
        query=query_text,
    )
    return [ProductCatalogSearchResponseSchema(**item) for item in results]


@router.get(
    "/api/v1/stores/{store_id}/products/search",
    response_model=List[ProductCatalogSearchResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="Search store catalog products under store scoping with map placement status",
)
def search_store_products_with_map_status_endpoint(
    store_id: str,
    query: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> List[ProductCatalogSearchResponseSchema]:
    query_text = search or query or ""
    results = MapService.search_store_catalog_with_map(
        db=db,
        store_id=store_id,
        query=query_text,
    )
    return [ProductCatalogSearchResponseSchema(**item) for item in results]


@router.get(
    "/api/v1/floors/{floor_id}/revisions",
    response_model=List[FloorRevisionResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="Get floor plan revision history",
)
@router.get(
    "/api/v1/stores/{store_id}/floors/{floor_id}/revisions",
    response_model=List[FloorRevisionResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="Get floor plan revision history under store scoping",
)
def get_floor_revisions_endpoint(
    floor_id: str,
    store_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> List[FloorRevisionResponseSchema]:
    revisions = MapService.get_floor_revisions(
        db=db,
        floor_id=floor_id,
        store_id=store_id,
    )
    return [FloorRevisionResponseSchema(**rev) for rev in revisions]


