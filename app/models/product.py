import uuid
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import backref, relationship
from sqlalchemy.sql import func
from app.db.session import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class StoreProduct(Base):
    __tablename__ = "store_products"

    id = Column(String, primary_key=True, default=generate_uuid, index=True)
    store_id = Column(String, nullable=False, index=True)
    store_sku = Column(String, nullable=False, index=True)
    barcode = Column(String, nullable=True, index=True)
    product_name = Column(String, nullable=False, index=True)
    category = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    stock_status = Column(String, nullable=False, default="IN_STOCK")
    quantity = Column(Integer, nullable=False, default=0)
    zone = Column(String, nullable=False)
    aisle = Column(String, nullable=False)
    rack = Column(String, nullable=True)
    shelf = Column(String, nullable=True)
    map_target = Column(String, nullable=False)
    map_target_node_id = Column(
        UUID(as_uuid=False),
        ForeignKey("map_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime, nullable=True, default=func.now())
    updated_at = Column(DateTime, nullable=True, default=func.now(), onupdate=func.now())

    # Relationships
    map_target_node = relationship("MapNode", back_populates="store_products")


class ProductLocation(Base):
    __tablename__ = "product_locations"

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
    product_id = Column(
        String,
        ForeignKey("store_products.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    zone = Column(String, nullable=True)
    aisle = Column(String, nullable=True)
    rack = Column(String, nullable=True)
    shelf = Column(String, nullable=True)
    map_target = Column(String, nullable=True)
    map_target_node_id = Column(
        UUID(as_uuid=False),
        ForeignKey("map_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
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
    map_target_node = relationship("MapNode", back_populates="product_locations")
    product = relationship("StoreProduct", backref=backref("locations", cascade="all, delete-orphan"))
    store = relationship("Store", backref=backref("product_locations", cascade="all, delete-orphan"))
