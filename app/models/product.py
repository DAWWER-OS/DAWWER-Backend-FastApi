import uuid
from sqlalchemy import Column, DateTime, Float, Integer, String
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
    created_at = Column(DateTime, nullable=True, default=func.now())
    updated_at = Column(DateTime, nullable=True, default=func.now(), onupdate=func.now())
