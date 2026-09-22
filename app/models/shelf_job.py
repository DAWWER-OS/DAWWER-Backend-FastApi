import uuid
from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.sql import func
from app.db.session import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class ShelfJob(Base):
    __tablename__ = "shelf_jobs"

    id = Column(String, primary_key=True, default=generate_uuid, index=True)
    store_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="PROCESSING")
    zone = Column(String, nullable=False)
    aisle = Column(String, nullable=False)
    rack = Column(String, nullable=True)
    shelf = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    extracted_drafts_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=True, default=func.now())
    updated_at = Column(DateTime, nullable=True, default=func.now(), onupdate=func.now())


class DraftProduct(Base):
    __tablename__ = "draft_products"

    id = Column(String, primary_key=True, default=generate_uuid, index=True)
    store_id = Column(String, nullable=False, index=True)
    shelf_job_id = Column(String, nullable=False, index=True)
    proposed_name = Column(String, nullable=False)
    estimated_price = Column(Float, nullable=False, default=0.0)
    category_hint = Column(String, nullable=True)
    pack_size = Column(String, nullable=True)
    barcode_detected = Column(String, nullable=True)
    confidence_score = Column(Float, nullable=False, default=0.0)
    zone = Column(String, nullable=True)
    aisle = Column(String, nullable=True)
    rack = Column(String, nullable=True)
    shelf = Column(String, nullable=True)
    status = Column(String, nullable=False, default="PENDING_REVIEW")
    created_at = Column(DateTime, nullable=True, default=func.now())
    updated_at = Column(DateTime, nullable=True, default=func.now(), onupdate=func.now())
