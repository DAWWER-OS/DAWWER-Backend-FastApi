from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.models.map_models import MapEdge, MapNode, MapNodeType, StoreMap
from app.models.product import ProductLocation, StoreProduct
from app.models.store import Store


class MapValidationError(HTTPException):
    """Custom exception raised when map graph fails structural publishing validation (HTTP 422)."""

    def __init__(self, errors: List[str]):
        detail = {
            "message": "Map validation failed: Cannot publish draft with structural errors",
            "errors": errors,
        }
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )
        self.errors = errors


class MapService:
    """Core service for StoreMap lifecycle, draft revisions, and batch element operations."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    @classmethod
    def get_or_create_draft_map(cls, db: Session, store_id: str) -> StoreMap:
        """Queries for an existing draft map (is_active=False) or creates a new revision draft."""
        if not store_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Store ID is required",
            )

        # 1. Query existing draft map for store
        draft_map = (
            db.query(StoreMap)
            .filter(
                StoreMap.store_id == str(store_id),
                StoreMap.is_active.is_(False),
            )
            .order_by(StoreMap.version.desc())
            .first()
        )
        if draft_map:
            return draft_map

        # 2. Determine revision version (increment from latest if exists)
        latest_map = (
            db.query(StoreMap)
            .filter(StoreMap.store_id == str(store_id))
            .order_by(StoreMap.version.desc())
            .first()
        )
        new_version = (latest_map.version + 1) if (latest_map and latest_map.version) else 1

        new_draft = StoreMap(
            id=str(uuid.uuid4()),
            store_id=str(store_id),
            version=new_version,
            floor_plan_image_url=None,
            width_meters=50.0,
            height_meters=50.0,
            is_active=False,
        )
        db.add(new_draft)
        db.commit()
        db.refresh(new_draft)
        return new_draft

    @classmethod
    def create_map_element(
        cls,
        db: Session,
        floor_id: str,
        element_data: Dict[str, Any],
        store_id: Optional[str] = None,
    ) -> MapNode:
        """Creates a single map node/element (shelf, wall, entrance, fridge) under a floor revision draft."""
        target_map = db.query(StoreMap).filter(StoreMap.id == str(floor_id)).first()
        if not target_map:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Floor/StoreMap '{floor_id}' not found",
            )

        if store_id and str(target_map.store_id).lower() != str(store_id).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted: Access denied under BR-14 store isolation policy",
            )

        assigned_id = str(element_data.get("id")) if element_data.get("id") else str(uuid.uuid4())
        label = str(element_data.get("label", "New Element"))
        x_coord = float(element_data.get("x_coord", element_data.get("x", 0.0)))
        y_coord = float(element_data.get("y_coord", element_data.get("y", 0.0)))

        raw_type = element_data.get("node_type", element_data.get("type", MapNodeType.SHELF_TARGET.value))
        if hasattr(raw_type, "value"):
            node_type = str(raw_type.value)
        else:
            node_type = str(raw_type)

        new_node = MapNode(
            id=assigned_id,
            map_id=str(floor_id),
            label=label,
            x_coord=x_coord,
            y_coord=y_coord,
            node_type=node_type,
            zone=element_data.get("zone"),
            aisle=element_data.get("aisle"),
            is_active=bool(element_data.get("is_active", True)),
        )
        db.add(new_node)
        target_map.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(new_node)
        return new_node

    @classmethod
    def update_map_element(
        cls,
        db: Session,
        element_id: str,
        update_data: Dict[str, Any],
        store_id: Optional[str] = None,
    ) -> MapNode:
        """Partially updates spatial coordinates, dimensions, or label of a specific element."""
        element = db.query(MapNode).filter(MapNode.id == str(element_id)).first()
        if not element:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Map element '{element_id}' not found",
            )

        target_map = db.query(StoreMap).filter(StoreMap.id == str(element.map_id)).first()
        if store_id and target_map and str(target_map.store_id).lower() != str(store_id).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted: Access denied under BR-14 store isolation policy",
            )

        if "label" in update_data and update_data["label"] is not None:
            element.label = str(update_data["label"])

        if "x_coord" in update_data and update_data["x_coord"] is not None:
            element.x_coord = float(update_data["x_coord"])
        elif "x" in update_data and update_data["x"] is not None:
            element.x_coord = float(update_data["x"])

        if "y_coord" in update_data and update_data["y_coord"] is not None:
            element.y_coord = float(update_data["y_coord"])
        elif "y" in update_data and update_data["y"] is not None:
            element.y_coord = float(update_data["y"])

        if "node_type" in update_data and update_data["node_type"] is not None:
            raw_t = update_data["node_type"]
            element.node_type = str(raw_t.value) if hasattr(raw_t, "value") else str(raw_t)
        elif "type" in update_data and update_data["type"] is not None:
            raw_t = update_data["type"]
            element.node_type = str(raw_t.value) if hasattr(raw_t, "value") else str(raw_t)

        if "zone" in update_data:
            element.zone = update_data["zone"]
        if "aisle" in update_data:
            element.aisle = update_data["aisle"]
        if "is_active" in update_data and update_data["is_active"] is not None:
            element.is_active = bool(update_data["is_active"])

        if target_map:
            target_map.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(element)
        return element

    @classmethod
    def delete_map_element(
        cls,
        db: Session,
        element_id: str,
        store_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Deletes a map element after verifying active product placement safety constraints."""
        from app.models.product import ProductLocation, StoreProduct

        element = db.query(MapNode).filter(MapNode.id == str(element_id)).first()
        if not element:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Map element '{element_id}' not found",
            )

        target_map = db.query(StoreMap).filter(StoreMap.id == str(element.map_id)).first()
        if store_id and target_map and str(target_map.store_id).lower() != str(store_id).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted: Access denied under BR-14 store isolation policy",
            )

        # Safety constraint check: Check active product placements
        active_products_count = (
            db.query(StoreProduct)
            .filter(
                StoreProduct.map_target_node_id == str(element_id),
                StoreProduct.is_active.is_(True),
            )
            .count()
        )
        active_locations_count = (
            db.query(ProductLocation)
            .filter(
                ProductLocation.map_target_node_id == str(element_id),
                ProductLocation.is_active.is_(True),
            )
            .count()
        )

        if active_products_count > 0 or active_locations_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete shelf containing active product placements",
            )

        # Delete any connected edges first to maintain referential integrity
        db.query(MapEdge).filter(
            (MapEdge.from_node_id == str(element_id)) | (MapEdge.to_node_id == str(element_id))
        ).delete(synchronize_session=False)

        db.delete(element)
        if target_map:
            target_map.updated_at = datetime.now(timezone.utc)

        db.commit()
        return {
            "status": "success",
            "message": f"Element '{element_id}' deleted successfully",
            "element_id": str(element_id),
        }

    @classmethod
    def get_shelf_layout(
        cls,
        db: Session,
        shelf_id: str,
        store_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieves structural shelf layout parameters and attached navigation access points."""
        element = db.query(MapNode).filter(MapNode.id == str(shelf_id)).first()
        if not element:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Shelf '{shelf_id}' not found",
            )

        target_map = db.query(StoreMap).filter(StoreMap.id == str(element.map_id)).first()
        if store_id and target_map and str(target_map.store_id).lower() != str(store_id).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted: Access denied under BR-14 store isolation policy",
            )

        sides = getattr(element, "_sides", 2)
        sections_count = getattr(element, "_sections_count", 4)
        levels_count = getattr(element, "_levels_count", 5)

        access_points = [
            {
                "side": "Side A",
                "label": f"{element.label} - Side A",
                "x_coord": round(element.x_coord, 2),
                "y_coord": round(max(0.0, element.y_coord - 0.5), 2),
            }
        ]
        if sides == 2:
            access_points.append(
                {
                    "side": "Side B",
                    "label": f"{element.label} - Side B",
                    "x_coord": round(element.x_coord, 2),
                    "y_coord": round(element.y_coord + 0.5, 2),
                }
            )

        return {
            "shelf_id": str(element.id),
            "map_id": str(element.map_id),
            "store_id": str(target_map.store_id) if target_map else None,
            "label": element.label,
            "x_coord": element.x_coord,
            "y_coord": element.y_coord,
            "sides": sides,
            "sections_count": sections_count,
            "levels_count": levels_count,
            "zone": element.zone,
            "aisle": element.aisle,
            "access_points": access_points,
        }

    @classmethod
    def update_shelf_layout(
        cls,
        db: Session,
        shelf_id: str,
        layout_data: Dict[str, Any],
        store_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates shelf physical parameters: sides (1 or 2), sections, levels, and access points."""
        element = db.query(MapNode).filter(MapNode.id == str(shelf_id)).first()
        if not element:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Shelf '{shelf_id}' not found",
            )

        target_map = db.query(StoreMap).filter(StoreMap.id == str(element.map_id)).first()
        if store_id and target_map and str(target_map.store_id).lower() != str(store_id).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted: Access denied under BR-14 store isolation policy",
            )

        if "label" in layout_data and layout_data["label"] is not None:
            element.label = str(layout_data["label"])
        if "x_coord" in layout_data and layout_data["x_coord"] is not None:
            element.x_coord = float(layout_data["x_coord"])
        if "y_coord" in layout_data and layout_data["y_coord"] is not None:
            element.y_coord = float(layout_data["y_coord"])
        if "zone" in layout_data:
            element.zone = layout_data["zone"]
        if "aisle" in layout_data:
            element.aisle = layout_data["aisle"]

        sides = layout_data.get("sides", getattr(element, "_sides", 2))
        sections_count = layout_data.get("sections_count", getattr(element, "_sections_count", 4))
        levels_count = layout_data.get("levels_count", getattr(element, "_levels_count", 5))

        setattr(element, "_sides", sides)
        setattr(element, "_sections_count", sections_count)
        setattr(element, "_levels_count", levels_count)

        if "access_points" in layout_data and layout_data["access_points"] is not None:
            raw_aps = layout_data["access_points"]
            access_points = []
            for ap in raw_aps:
                if isinstance(ap, dict):
                    access_points.append({
                        "side": ap.get("side", "Side A"),
                        "label": ap.get("label", f"{element.label} - Access Point"),
                        "x_coord": float(ap["x_coord"]),
                        "y_coord": float(ap["y_coord"]),
                    })
                else:
                    access_points.append({
                        "side": getattr(ap, "side", "Side A"),
                        "label": getattr(ap, "label", f"{element.label} - Access Point"),
                        "x_coord": float(ap.x_coord),
                        "y_coord": float(ap.y_coord),
                    })
        else:
            # Automatically recalculate access point spatial coordinates relative to shelf position
            access_points = [
                {
                    "side": "Side A",
                    "label": f"{element.label} - Side A",
                    "x_coord": round(element.x_coord, 2),
                    "y_coord": round(max(0.0, element.y_coord - 0.5), 2),
                }
            ]
            if sides == 2:
                access_points.append(
                    {
                        "side": "Side B",
                        "label": f"{element.label} - Side B",
                        "x_coord": round(element.x_coord, 2),
                        "y_coord": round(element.y_coord + 0.5, 2),
                    }
                )

        if target_map:
            target_map.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(element)

        return {
            "shelf_id": str(element.id),
            "map_id": str(element.map_id),
            "store_id": str(target_map.store_id) if target_map else None,
            "label": element.label,
            "x_coord": element.x_coord,
            "y_coord": element.y_coord,
            "sides": sides,
            "sections_count": sections_count,
            "levels_count": levels_count,
            "zone": element.zone,
            "aisle": element.aisle,
            "access_points": access_points,
        }

    @classmethod
    def save_elements_batch(
        cls,
        db: Session,
        store_id: str,
        map_id: str,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Atomically upserts or deletes nodes and edges for a store's map under BR-14 scoping."""
        target_map = db.query(StoreMap).filter(StoreMap.id == str(map_id)).first()
        if not target_map:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"StoreMap '{map_id}' not found",
            )

        if str(target_map.store_id).lower() != str(store_id).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted: Access denied under BR-14 store isolation policy",
            )

        try:
            node_lookup: Dict[str, MapNode] = {}
            existing_nodes = db.query(MapNode).filter(MapNode.map_id == str(map_id)).all()
            for en in existing_nodes:
                node_lookup[str(en.id)] = en

            for node_data in nodes:
                is_deleted = bool(
                    node_data.get("is_deleted")
                    or node_data.get("deleted")
                    or node_data.get("action") == "delete"
                    or node_data.get("_destroy")
                )
                node_id = str(node_data.get("id")) if node_data.get("id") else None

                if is_deleted:
                    if node_id and node_id in node_lookup:
                        db.delete(node_lookup[node_id])
                        del node_lookup[node_id]
                    continue

                if node_id and node_id in node_lookup:
                    node_obj = node_lookup[node_id]
                    if "label" in node_data:
                        node_obj.label = str(node_data["label"])
                    if "x_coord" in node_data:
                        node_obj.x_coord = float(node_data["x_coord"])
                    if "y_coord" in node_data:
                        node_obj.y_coord = float(node_data["y_coord"])
                    if "node_type" in node_data:
                        node_obj.node_type = str(node_data["node_type"])
                    if "zone" in node_data:
                        node_obj.zone = node_data["zone"]
                    if "aisle" in node_data:
                        node_obj.aisle = node_data["aisle"]
                    if "is_active" in node_data:
                        node_obj.is_active = bool(node_data["is_active"])
                else:
                    assigned_id = node_id or str(uuid.uuid4())
                    node_obj = MapNode(
                        id=assigned_id,
                        map_id=str(map_id),
                        label=str(node_data.get("label", "Node")),
                        x_coord=float(node_data.get("x_coord", 0.0)),
                        y_coord=float(node_data.get("y_coord", 0.0)),
                        node_type=str(node_data.get("node_type", MapNodeType.AISLE_JUNCTION.value)),
                        zone=node_data.get("zone"),
                        aisle=node_data.get("aisle"),
                        is_active=bool(node_data.get("is_active", True)),
                    )
                    db.add(node_obj)
                    node_lookup[assigned_id] = node_obj

            db.flush()

            edge_lookup: Dict[str, MapEdge] = {}
            existing_edges = db.query(MapEdge).filter(MapEdge.map_id == str(map_id)).all()
            for ee in existing_edges:
                edge_lookup[str(ee.id)] = ee

            for edge_data in edges:
                is_deleted = bool(
                    edge_data.get("is_deleted")
                    or edge_data.get("deleted")
                    or edge_data.get("action") == "delete"
                    or edge_data.get("_destroy")
                )
                edge_id = str(edge_data.get("id")) if edge_data.get("id") else None

                if is_deleted:
                    if edge_id and edge_id in edge_lookup:
                        db.delete(edge_lookup[edge_id])
                        del edge_lookup[edge_id]
                    continue

                from_nid = str(edge_data["from_node_id"])
                to_nid = str(edge_data["to_node_id"])

                dist = edge_data.get("distance_meters")
                if dist is None:
                    from_n = node_lookup.get(from_nid)
                    to_n = node_lookup.get(to_nid)
                    if from_n and to_n:
                        dist = round(math.hypot(to_n.x_coord - from_n.x_coord, to_n.y_coord - from_n.y_coord), 2)
                    else:
                        dist = 1.0
                else:
                    dist = float(dist)

                if edge_id and edge_id in edge_lookup:
                    edge_obj = edge_lookup[edge_id]
                    edge_obj.from_node_id = from_nid
                    edge_obj.to_node_id = to_nid
                    edge_obj.distance_meters = dist
                    if "weight" in edge_data:
                        edge_obj.weight = float(edge_data["weight"])
                    if "is_accessible" in edge_data:
                        edge_obj.is_accessible = bool(edge_data["is_accessible"])
                    if "is_blocked" in edge_data:
                        edge_obj.is_blocked = bool(edge_data["is_blocked"])
                else:
                    matched_edge = None
                    for ee in edge_lookup.values():
                        if str(ee.from_node_id) == from_nid and str(ee.to_node_id) == to_nid:
                            matched_edge = ee
                            break

                    if matched_edge:
                        matched_edge.distance_meters = dist
                        if "weight" in edge_data:
                            matched_edge.weight = float(edge_data["weight"])
                        if "is_accessible" in edge_data:
                            matched_edge.is_accessible = bool(edge_data["is_accessible"])
                        if "is_blocked" in edge_data:
                            matched_edge.is_blocked = bool(edge_data["is_blocked"])
                    else:
                        assigned_edge_id = edge_id or str(uuid.uuid4())
                        edge_obj = MapEdge(
                            id=assigned_edge_id,
                            map_id=str(map_id),
                            from_node_id=from_nid,
                            to_node_id=to_nid,
                            distance_meters=dist,
                            weight=float(edge_data.get("weight", 1.0)),
                            is_accessible=bool(edge_data.get("is_accessible", True)),
                            is_blocked=bool(edge_data.get("is_blocked", False)),
                        )
                        db.add(edge_obj)
                        edge_lookup[assigned_edge_id] = edge_obj

            target_map.updated_at = datetime.now(timezone.utc)
            db.commit()

            return {
                "status": "success",
                "nodes_processed": len(nodes),
                "edges_processed": len(edges),
            }

        except HTTPException:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Transaction failed while batch saving map elements: {str(exc)}",
            )

    @classmethod
    def validate_map_graph(cls, db: Session, store_id: str, map_id: str) -> Dict[str, Any]:
        """Validates structural correctness of a store map before publishing."""
        target_map = db.query(StoreMap).filter(StoreMap.id == str(map_id)).first()
        if not target_map:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"StoreMap '{map_id}' not found",
            )

        if str(target_map.store_id).lower() != str(store_id).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted: Access denied under BR-14 store isolation policy",
            )

        errors: List[str] = []
        nodes = db.query(MapNode).filter(MapNode.map_id == str(map_id)).all()
        edges = db.query(MapEdge).filter(MapEdge.map_id == str(map_id)).all()

        if not nodes:
            errors.append("Map contains no nodes. At least one ENTRANCE_QR node is required.")
        else:
            has_entrance = any(
                n.node_type == MapNodeType.ENTRANCE_QR.value or str(n.node_type).upper() == "ENTRANCE_QR"
                for n in nodes
            )
            if not has_entrance:
                errors.append("Map must contain at least one ENTRANCE_QR node.")

            width_m = float(target_map.width_meters or 50.0)
            height_m = float(target_map.height_meters or 50.0)
            node_ids = set()

            for node in nodes:
                node_ids.add(str(node.id))
                x = float(node.x_coord)
                y = float(node.y_coord)
                if x < 0.0 or x > width_m or y < 0.0 or y > height_m:
                    errors.append(
                        f"Node '{node.label}' ({node.id}) coordinates ({x}, {y}) are outside map boundary [0..{width_m}, 0..{height_m}]."
                    )

            for edge in edges:
                if str(edge.from_node_id) not in node_ids:
                    errors.append(f"Edge ({edge.id}) source from_node_id '{edge.from_node_id}' does not exist in map.")
                if str(edge.to_node_id) not in node_ids:
                    errors.append(f"Edge ({edge.id}) destination to_node_id '{edge.to_node_id}' does not exist in map.")
                if float(edge.distance_meters) < 0.0:
                    errors.append(f"Edge ({edge.id}) has invalid negative distance: {edge.distance_meters}m.")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
        }

    @classmethod
    def publish_map_revision(cls, db: Session, store_id: str, map_id: str) -> StoreMap:
        """Publishes a draft map revision, validating its graph structure and activating it."""
        target_map = db.query(StoreMap).filter(StoreMap.id == str(map_id)).first()
        if not target_map:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"StoreMap '{map_id}' not found",
            )

        if str(target_map.store_id).lower() != str(store_id).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted: Access denied under BR-14 store isolation policy",
            )

        validation_result = cls.validate_map_graph(db, store_id=store_id, map_id=map_id)
        if not validation_result["is_valid"]:
            raise MapValidationError(errors=validation_result["errors"])

        try:
            db.query(StoreMap).filter(
                StoreMap.store_id == str(store_id),
                StoreMap.is_active.is_(True),
            ).update({"is_active": False}, synchronize_session=False)

            target_map.is_active = True
            target_map.updated_at = datetime.now(timezone.utc)

            db.commit()
            db.refresh(target_map)
            return target_map

        except Exception as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to publish map revision: {str(exc)}",
            )

    @classmethod
    def create_product_placement(
        cls,
        db: Session,
        store_id: str,
        placement_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Links a catalog product (StoreProduct / ProductLocation) to a specific map node / shelf ID, section, and level."""
        product_id = placement_data.get("product_id")
        shelf_id = placement_data.get("shelf_id") or placement_data.get("map_target_node_id")

        if not product_id or not shelf_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="product_id and shelf_id are required fields",
            )

        # Enforce store scoping (BR-14)
        payload_store_id = placement_data.get("store_id")
        if payload_store_id and str(payload_store_id).lower() != str(store_id).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted: Access denied under BR-14 store isolation policy",
            )

        # Retrieve shelf node and verify store ownership
        shelf_node = db.query(MapNode).filter(MapNode.id == str(shelf_id)).first()
        if not shelf_node:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Shelf node '{shelf_id}' not found",
            )

        target_map = db.query(StoreMap).filter(StoreMap.id == str(shelf_node.map_id)).first()
        if target_map and str(target_map.store_id).lower() != str(store_id).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted: Access denied under BR-14 store isolation policy",
            )

        # Retrieve catalog product and verify store ownership if product exists
        product = db.query(StoreProduct).filter(StoreProduct.id == str(product_id)).first()
        if product and str(product.store_id).lower() != str(store_id).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted: Access denied under BR-14 store isolation policy",
            )

        section_str = str(placement_data.get("section") or placement_data.get("rack") or "1")
        level_str = str(placement_data.get("level") or placement_data.get("shelf") or "1")
        aisle_str = str(placement_data.get("aisle") or shelf_node.aisle or "Aisle 1")
        zone_str = str(placement_data.get("zone") or shelf_node.zone or "")

        formatted_location = placement_data.get("map_target") or placement_data.get("location_code")
        if not formatted_location:
            shelf_label = shelf_node.label if shelf_node.label else "Shelf"
            formatted_location = f"{aisle_str} - {shelf_label} - Level {level_str}"

        # Update StoreProduct map attributes if present
        if product:
            product.map_target_node_id = str(shelf_node.id)
            product.map_target = formatted_location
            product.zone = zone_str
            product.aisle = aisle_str
            product.rack = section_str
            product.shelf = level_str

        # Create ProductLocation record
        location_id = str(uuid.uuid4())
        location = ProductLocation(
            id=location_id,
            store_id=str(store_id),
            product_id=str(product_id),
            map_target_node_id=str(shelf_node.id),
            zone=zone_str,
            aisle=aisle_str,
            rack=section_str,
            shelf=level_str,
            map_target=formatted_location,
            is_active=bool(placement_data.get("is_active", True)),
        )
        db.add(location)
        db.commit()
        db.refresh(location)

        return {
            "placement_id": str(location.id),
            "id": str(location.id),
            "product_id": str(location.product_id),
            "store_id": str(location.store_id),
            "shelf_id": str(location.map_target_node_id),
            "map_target_node_id": str(location.map_target_node_id),
            "zone": location.zone,
            "aisle": location.aisle,
            "section": location.rack,
            "rack": location.rack,
            "level": location.shelf,
            "shelf": location.shelf,
            "location_code": location.map_target,
            "map_target": location.map_target,
            "x_coord": float(shelf_node.x_coord),
            "y_coord": float(shelf_node.y_coord),
            "is_active": location.is_active,
            "created_at": location.created_at,
            "updated_at": location.updated_at,
        }

    @classmethod
    def update_product_placement(
        cls,
        db: Session,
        placement_id: str,
        update_data: Dict[str, Any],
        store_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Moves a product from one shelf slot/level to another or assigns it to a new map node."""
        location = db.query(ProductLocation).filter(ProductLocation.id == str(placement_id)).first()
        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product placement location '{placement_id}' not found",
            )

        if store_id and str(location.store_id).lower() != str(store_id).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted: Access denied under BR-14 store isolation policy",
            )

        eff_store_id = store_id or str(location.store_id)
        shelf_id = update_data.get("shelf_id") or update_data.get("map_target_node_id")

        if shelf_id:
            shelf_node = db.query(MapNode).filter(MapNode.id == str(shelf_id)).first()
            if not shelf_node:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Shelf node '{shelf_id}' not found",
                )
            target_map = db.query(StoreMap).filter(StoreMap.id == str(shelf_node.map_id)).first()
            if target_map and str(target_map.store_id).lower() != str(eff_store_id).lower():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Operation not permitted: Access denied under BR-14 store isolation policy",
                )
            location.map_target_node_id = str(shelf_node.id)
        else:
            shelf_node = db.query(MapNode).filter(MapNode.id == str(location.map_target_node_id)).first() if location.map_target_node_id else None

        if "section" in update_data and update_data["section"] is not None:
            location.rack = str(update_data["section"])
        elif "rack" in update_data and update_data["rack"] is not None:
            location.rack = str(update_data["rack"])

        if "level" in update_data and update_data["level"] is not None:
            location.shelf = str(update_data["level"])
        elif "shelf" in update_data and update_data["shelf"] is not None:
            location.shelf = str(update_data["shelf"])

        if "zone" in update_data:
            location.zone = update_data["zone"]
        if "aisle" in update_data:
            location.aisle = update_data["aisle"]
        if "is_active" in update_data and update_data["is_active"] is not None:
            location.is_active = bool(update_data["is_active"])

        formatted_location = update_data.get("map_target") or update_data.get("location_code")
        if formatted_location:
            location.map_target = formatted_location
        elif shelf_node:
            aisle_str = location.aisle or shelf_node.aisle or "Aisle 1"
            shelf_label = shelf_node.label if shelf_node.label else "Shelf"
            level_str = location.shelf or "1"
            location.map_target = f"{aisle_str} - {shelf_label} - Level {level_str}"

        # Sync StoreProduct if linked
        if location.product_id:
            product = db.query(StoreProduct).filter(StoreProduct.id == str(location.product_id)).first()
            if product:
                product.map_target_node_id = location.map_target_node_id
                product.map_target = location.map_target
                if location.zone:
                    product.zone = location.zone
                if location.aisle:
                    product.aisle = location.aisle
                if location.rack:
                    product.rack = location.rack
                if location.shelf:
                    product.shelf = location.shelf

        db.commit()
        db.refresh(location)

        x_coord = float(shelf_node.x_coord) if shelf_node else 0.0
        y_coord = float(shelf_node.y_coord) if shelf_node else 0.0

        return {
            "placement_id": str(location.id),
            "id": str(location.id),
            "product_id": str(location.product_id),
            "store_id": str(location.store_id),
            "shelf_id": str(location.map_target_node_id),
            "map_target_node_id": str(location.map_target_node_id),
            "zone": location.zone,
            "aisle": location.aisle,
            "section": location.rack,
            "rack": location.rack,
            "level": location.shelf,
            "shelf": location.shelf,
            "location_code": location.map_target,
            "map_target": location.map_target,
            "x_coord": x_coord,
            "y_coord": y_coord,
            "is_active": location.is_active,
            "created_at": location.created_at,
            "updated_at": location.updated_at,
        }

    @classmethod
    def delete_product_placement(
        cls,
        db: Session,
        placement_id: str,
        store_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Unlinks the product from the map shelf node without deleting the product entry from the catalog."""
        location = db.query(ProductLocation).filter(ProductLocation.id == str(placement_id)).first()
        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product placement location '{placement_id}' not found",
            )

        if store_id and str(location.store_id).lower() != str(store_id).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted: Access denied under BR-14 store isolation policy",
            )

        # Unlink associated StoreProduct map target
        if location.product_id:
            product = db.query(StoreProduct).filter(StoreProduct.id == str(location.product_id)).first()
            if product:
                product.map_target_node_id = None

        location.map_target_node_id = None
        location.is_active = False

        prod_id = str(location.product_id) if location.product_id else None
        try:
            logger.info("Committing unlinking/deletion of product placement %s", placement_id)
            db.delete(location)
            db.commit()
            logger.info("Successfully committed unlinking of product placement %s", placement_id)
        except Exception as exc:
            db.rollback()
            logger.error("Database error unlinking product placement %s: %s", placement_id, exc)
            raise

        return {
            "status": "success",
            "message": "Product placement unlinked successfully from map shelf",
            "placement_id": str(placement_id),
            "product_id": prod_id,
            "deleted": True,
        }

    @classmethod
    def get_product_locations(
        cls,
        db: Session,
        store_id: str,
        product_id: str,
    ) -> List[Dict[str, Any]]:
        """Retrieves all active published floor locations and coordinates for a given product ID."""
        product = db.query(StoreProduct).filter(StoreProduct.id == str(product_id)).first()
        if product and str(product.store_id).lower() != str(store_id).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted: Access denied under BR-14 store isolation policy",
            )

        locations = (
            db.query(ProductLocation)
            .filter(
                ProductLocation.product_id == str(product_id),
                ProductLocation.store_id == str(store_id),
                ProductLocation.is_active.is_(True),
            )
            .all()
        )

        results: List[Dict[str, Any]] = []
        for loc in locations:
            shelf_node = (
                db.query(MapNode).filter(MapNode.id == str(loc.map_target_node_id)).first()
                if loc.map_target_node_id
                else None
            )
            x_coord = float(shelf_node.x_coord) if shelf_node else 0.0
            y_coord = float(shelf_node.y_coord) if shelf_node else 0.0

            results.append(
                {
                    "placement_id": str(loc.id),
                    "id": str(loc.id),
                    "product_id": str(loc.product_id),
                    "store_id": str(loc.store_id),
                    "shelf_id": str(loc.map_target_node_id) if loc.map_target_node_id else None,
                    "map_target_node_id": str(loc.map_target_node_id) if loc.map_target_node_id else None,
                    "zone": loc.zone,
                    "aisle": loc.aisle,
                    "section": loc.rack,
                    "rack": loc.rack,
                    "level": loc.shelf,
                    "shelf": loc.shelf,
                    "location_code": loc.map_target,
                    "map_target": loc.map_target,
                    "x_coord": x_coord,
                    "y_coord": y_coord,
                    "is_active": loc.is_active,
                    "created_at": loc.created_at,
                    "updated_at": loc.updated_at,
                }
            )

        # Fallback if no ProductLocation record but StoreProduct has map_target_node_id
        if not results and product and product.map_target_node_id:
            shelf_node = db.query(MapNode).filter(MapNode.id == str(product.map_target_node_id)).first()
            if shelf_node:
                results.append(
                    {
                        "placement_id": str(uuid.uuid4()),
                        "id": str(uuid.uuid4()),
                        "product_id": str(product.id),
                        "store_id": str(product.store_id),
                        "shelf_id": str(product.map_target_node_id),
                        "map_target_node_id": str(product.map_target_node_id),
                        "zone": product.zone,
                        "aisle": product.aisle,
                        "section": product.rack,
                        "rack": product.rack,
                        "level": product.shelf,
                        "shelf": product.shelf,
                        "location_code": product.map_target,
                        "map_target": product.map_target,
                        "x_coord": float(shelf_node.x_coord),
                        "y_coord": float(shelf_node.y_coord),
                        "is_active": True,
                        "created_at": product.created_at,
                        "updated_at": product.updated_at,
                    }
                )

        return results

    @classmethod
    def search_store_catalog_with_map(
        cls,
        db: Session,
        store_id: str,
        query: str,
    ) -> List[Dict[str, Any]]:
        """Searches store products matching query text and flags each item with availableInStore based on active floor map node placement."""
        if not store_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="store_id parameter is required for catalog search",
            )

        # 1. Fetch active published StoreMap for the store
        active_map = (
            db.query(StoreMap)
            .filter(
                StoreMap.store_id == str(store_id),
                StoreMap.is_active.is_(True),
            )
            .first()
        )

        active_node_ids = set()
        if active_map:
            nodes = (
                db.query(MapNode.id)
                .filter(
                    MapNode.map_id == str(active_map.id),
                    MapNode.is_active.is_(True),
                )
                .all()
            )
            active_node_ids = {str(n[0]) for n in nodes}

        # Collect active ProductLocation node links for store
        active_placements = (
            db.query(ProductLocation)
            .filter(
                ProductLocation.store_id == str(store_id),
                ProductLocation.is_active.is_(True),
            )
            .all()
        )
        product_placement_node_map = {}
        for pl in active_placements:
            if pl.product_id and pl.map_target_node_id:
                product_placement_node_map[str(pl.product_id)] = str(pl.map_target_node_id)

        # 2. Query products for store matching query
        query_builder = db.query(StoreProduct).filter(
            StoreProduct.store_id == str(store_id),
            StoreProduct.is_active.is_(True),
        )

        if query and query.strip():
            search_pattern = f"%{query.strip()}%"
            query_builder = query_builder.filter(
                (StoreProduct.product_name.ilike(search_pattern))
                | (StoreProduct.category.ilike(search_pattern))
                | (StoreProduct.barcode.ilike(search_pattern))
                | (StoreProduct.store_sku.ilike(search_pattern))
            )

        products = query_builder.all()

        results: List[Dict[str, Any]] = []
        for p in products:
            target_node_id = str(p.map_target_node_id) if p.map_target_node_id else product_placement_node_map.get(str(p.id))
            is_placed_on_active_map = bool(target_node_id and target_node_id in active_node_ids)

            results.append(
                {
                    "id": str(p.id),
                    "product_id": str(p.id),
                    "store_id": str(p.store_id),
                    "product_name": p.product_name,
                    "category": p.category,
                    "price": float(p.price or 0.0),
                    "stock_status": p.stock_status or "IN_STOCK",
                    "quantity": int(p.quantity or 0),
                    "zone": p.zone,
                    "aisle": p.aisle,
                    "rack": p.rack,
                    "shelf": p.shelf,
                    "map_target": p.map_target,
                    "map_target_node_id": target_node_id,
                    "availableInStore": is_placed_on_active_map,
                    "available_in_store": is_placed_on_active_map,
                    "is_active": p.is_active,
                }
            )

        return results

    @classmethod
    def get_floor_revisions(
        cls,
        db: Session,
        floor_id: str,
        store_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieves version history and publication timestamps of all StoreMap revisions for the floor/store."""
        target_map = db.query(StoreMap).filter(StoreMap.id == str(floor_id)).first()
        eff_store_id = store_id

        if target_map:
            if store_id and str(target_map.store_id).lower() != str(store_id).lower():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Operation not permitted: Access denied under BR-14 store isolation policy",
                )
            eff_store_id = str(target_map.store_id)

        if not eff_store_id:
            eff_store_id = str(floor_id)

        revisions = (
            db.query(StoreMap)
            .filter(StoreMap.store_id == str(eff_store_id))
            .order_by(StoreMap.version.desc())
            .all()
        )

        if not revisions and target_map:
            revisions = [target_map]

        results = []
        for m in revisions:
            results.append(
                {
                    "id": str(m.id),
                    "map_id": str(m.id),
                    "store_id": str(m.store_id),
                    "version": m.version,
                    "is_active": m.is_active,
                    "floor_plan_image_url": m.floor_plan_image_url,
                    "width_meters": float(m.width_meters or 50.0),
                    "height_meters": float(m.height_meters or 50.0),
                    "created_at": m.created_at,
                    "updated_at": m.updated_at,
                }
            )

        return results


