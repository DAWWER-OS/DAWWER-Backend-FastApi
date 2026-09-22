import uuid
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.session import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Category(Base):
    __tablename__ = "categories"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
        index=True,
    )
    name = Column(String, nullable=False, index=True)
    description = Column(String, nullable=True)
    icon_url = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    display_order = Column(Integer, nullable=False, default=0, server_default=text("0"))
    parent_category_id = Column(
        UUID(as_uuid=False),
        ForeignKey("categories.id"),
        nullable=True,
        index=True,
    )
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
    created_by = Column(Text, nullable=True)
    updated_by = Column(Text, nullable=True)
