import uuid
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, func
from app.db.session import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Store(Base):
    __tablename__ = "stores"

    id = Column(String, primary_key=True, default=generate_uuid, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(String, nullable=True)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    status = Column(String, default="PENDING", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
