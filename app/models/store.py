import uuid
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.session import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Store(Base):
    __tablename__ = "stores"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
        index=True,
    )
    owner_id = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    name = Column(String, nullable=False, index=True)
    description = Column(String, nullable=True)
    commercial_registration_number = Column(String, nullable=True)
    tax_number = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    email = Column(String, nullable=True)
    address = Column(String, nullable=True)
    city = Column(String, nullable=True)
    latitude = Column(Numeric, nullable=True)
    longitude = Column(Numeric, nullable=True)
    logo_url = Column(String, nullable=True)
    cover_image_url = Column(String, nullable=True)
    verification_status = Column(String, nullable=False, default="APPROVED")
    status = Column(String, nullable=False, default="PENDING")
    rejection_reason = Column(String, nullable=True)
    information_request_message = Column(String, nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_id = Column(UUID(as_uuid=False), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    suspended_at = Column(DateTime(timezone=True), nullable=True)
    suspension_reason = Column(String, nullable=True)
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
    is_active = Column(Boolean, nullable=True, default=True, server_default=text("true"))
