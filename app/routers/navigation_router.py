from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.map_schemas import (
    NavigationRouteRequestSchema,
    NavigationRouteResponseSchema,
)
from app.services.navigation_service import (
    LocationResolutionError,
    NavigationService,
    StoreMapNotFoundError,
    UnreachableDestinationError,
)

router = APIRouter(
    prefix="/api/v1/stores/{store_id}/routes",
    tags=["Navigation & Routing"],
)


class MultiStopRouteRequestSchema(BaseModel):
    start_node_id: Optional[str] = Field(default=None, description="Starting node UUID")
    start_qr_code: Optional[str] = Field(default=None, description="Scanned QR code label/identifier at entrance or checkpoint")
    start_spec: Optional[Dict[str, Any]] = Field(default=None, description="Optional raw start specification dictionary")
    product_ids: List[str] = Field(default_factory=list, description="Shopping basket product IDs")
    avoid_crowded_edges: bool = Field(default=True, description="Whether to apply edge weighting to avoid crowded aisles")


@router.post(
    "/shortest",
    response_model=NavigationRouteResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Calculate single-destination shortest path",
    description="Accepts route specifications (start QR code, start node ID, target node ID, target product IDs) and calculates the optimal 2D floor path with turn-by-turn guidance.",
)
def calculate_shortest_route(
    store_id: str,
    payload: NavigationRouteRequestSchema,
    db: Session = Depends(get_db),
) -> NavigationRouteResponseSchema:
    start_spec: Dict[str, Any] = {}
    if payload.start_qr_code:
        start_spec["start_qr_code"] = payload.start_qr_code
    if payload.start_node_id:
        start_spec["start_node_id"] = payload.start_node_id

    destination_spec: Dict[str, Any] = {}
    if payload.target_node_id:
        destination_spec["target_node_id"] = payload.target_node_id
    elif payload.target_product_ids and len(payload.target_product_ids) > 0:
        destination_spec["target_product_id"] = payload.target_product_ids[0]

    nav_service = NavigationService(db)

    try:
        route = nav_service.calculate_shortest_path(
            store_id=store_id,
            start_spec=start_spec,
            destination_spec=destination_spec,
            avoid_crowded=payload.avoid_crowded_edges,
        )
        return NavigationRouteResponseSchema(**route)

    except (UnreachableDestinationError, LocationResolutionError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except StoreMapNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.post(
    "/optimize",
    response_model=NavigationRouteResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Optimize multi-stop shopping route terminating at cashier",
    description="Accepts a shopping basket list of product IDs, calculates the optimal visiting sequence using Nearest-Neighbor + 2-opt swap, and terminates at the nearest cashier checkout counter.",
)
def optimize_multi_stop_route(
    store_id: str,
    payload: MultiStopRouteRequestSchema,
    db: Session = Depends(get_db),
) -> NavigationRouteResponseSchema:
    start_spec: Dict[str, Any] = payload.start_spec or {}
    if payload.start_qr_code:
        start_spec["start_qr_code"] = payload.start_qr_code
    if payload.start_node_id:
        start_spec["start_node_id"] = payload.start_node_id

    nav_service = NavigationService(db)

    try:
        route = nav_service.optimize_multi_stop_route(
            store_id=store_id,
            start_spec=start_spec,
            product_ids=payload.product_ids,
            avoid_crowded=payload.avoid_crowded_edges,
        )
        return NavigationRouteResponseSchema(**route)

    except (UnreachableDestinationError, LocationResolutionError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except StoreMapNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
