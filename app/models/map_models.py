import enum
import uuid
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import backref, relationship
from sqlalchemy.sql import func
from app.db.session import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class MapNodeType(str, enum.Enum):
    ENTRANCE_QR = "ENTRANCE_QR"
    CHECKPOINT_QR = "CHECKPOINT_QR"
    AISLE_JUNCTION = "AISLE_JUNCTION"
    SHELF_TARGET = "SHELF_TARGET"
    CASHIER = "CASHIER"


class StoreMap(Base):
    __tablename__ = "store_maps"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
        index=True,
    )
    store_id = Column(
        UUID(as_uuid=False),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False, default=1, server_default=text("1"))
    floor_plan_image_url = Column(String, nullable=True)
    width_meters = Column(Float, nullable=False, default=50.0, server_default=text("50.0"))
    height_meters = Column(Float, nullable=False, default=50.0, server_default=text("50.0"))
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=text("now()"),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
    )

    # Relationships
    store = relationship("Store", backref=backref("maps", cascade="all, delete-orphan"))
    nodes = relationship("MapNode", back_populates="store_map", cascade="all, delete-orphan")
    edges = relationship("MapEdge", back_populates="store_map", cascade="all, delete-orphan")


class MapNode(Base):
    __tablename__ = "map_nodes"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
        index=True,
    )
    map_id = Column(
        UUID(as_uuid=False),
        ForeignKey("store_maps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_type = Column(
        String,
        nullable=False,
        default=MapNodeType.AISLE_JUNCTION.value,
        server_default=text("'AISLE_JUNCTION'"),
    )
    label = Column(String, nullable=False)
    x_coord = Column(Float, nullable=False)
    y_coord = Column(Float, nullable=False)
    zone = Column(String, nullable=True)
    aisle = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=text("now()"),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
    )

    # Relationships
    store_map = relationship("StoreMap", back_populates="nodes")
    outgoing_edges = relationship(
        "MapEdge",
        foreign_keys="MapEdge.from_node_id",
        back_populates="from_node",
        cascade="all, delete-orphan",
    )
    incoming_edges = relationship(
        "MapEdge",
        foreign_keys="MapEdge.to_node_id",
        back_populates="to_node",
        cascade="all, delete-orphan",
    )
    product_locations = relationship(
        "ProductLocation",
        back_populates="map_target_node",
    )
    store_products = relationship(
        "StoreProduct",
        back_populates="map_target_node",
    )


class MapEdge(Base):
    __tablename__ = "map_edges"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
        index=True,
    )
    map_id = Column(
        UUID(as_uuid=False),
        ForeignKey("store_maps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_node_id = Column(
        UUID(as_uuid=False),
        ForeignKey("map_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_node_id = Column(
        UUID(as_uuid=False),
        ForeignKey("map_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    distance_meters = Column(Float, nullable=False)
    weight = Column(Float, nullable=False, default=1.0, server_default=text("1.0"))
    is_accessible = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    is_blocked = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=text("now()"),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
    )

    # Relationships
    store_map = relationship("StoreMap", back_populates="edges")
    from_node = relationship(
        "MapNode",
        foreign_keys=[from_node_id],
        back_populates="outgoing_edges",
    )
    to_node = relationship(
        "MapNode",
        foreign_keys=[to_node_id],
        back_populates="incoming_edges",
    )
