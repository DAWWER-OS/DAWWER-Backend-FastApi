import uuid
from sqlalchemy import Boolean, Column, DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.session import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
        index=True,
    )
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True, index=True)
    phone_number = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    status = Column(String, nullable=False, default="Active")
    is_email_verified = Column(Boolean, nullable=False, default=False)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    is_phone_verified = Column(Boolean, nullable=False, default=False)
    phone_verified_at = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
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
