import uuid
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.session import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class StoreRole(Base):
    __tablename__ = "store_roles"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
        index=True,
    )
    store_id = Column(
        UUID(as_uuid=False),
        ForeignKey("stores.id"),
        nullable=True,
        index=True,
    )
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    is_system_role = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=text("now()"),
    )
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    created_by = Column(Text, nullable=True)
    updated_by = Column(Text, nullable=True)


class StorePermission(Base):
    __tablename__ = "store_permissions"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
        index=True,
    )
    code = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=text("now()"),
    )
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    created_by = Column(Text, nullable=True)
    updated_by = Column(Text, nullable=True)


class StoreRolePermission(Base):
    __tablename__ = "store_role_permissions"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
        index=True,
    )
    store_role_id = Column(
        UUID(as_uuid=False),
        ForeignKey("store_roles.id"),
        nullable=False,
        index=True,
    )
    store_permission_id = Column(
        UUID(as_uuid=False),
        ForeignKey("store_permissions.id"),
        nullable=False,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=text("now()"),
    )
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    created_by = Column(Text, nullable=True)
    updated_by = Column(Text, nullable=True)


class StoreStaff(Base):
    __tablename__ = "store_staff"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
        index=True,
    )
    store_id = Column(
        UUID(as_uuid=False),
        ForeignKey("stores.id"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    store_role_id = Column(
        UUID(as_uuid=False),
        ForeignKey("store_roles.id"),
        nullable=False,
        index=True,
    )
    status = Column(String, nullable=False, default="Active")
    assigned_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=text("now()"),
    )
    assigned_by_id = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id"),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=text("now()"),
    )
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    created_by = Column(Text, nullable=True)
    updated_by = Column(Text, nullable=True)


class StoreStaffPermission(Base):
    __tablename__ = "store_staff_permissions"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
        index=True,
    )
    store_staff_id = Column(
        UUID(as_uuid=False),
        ForeignKey("store_staff.id"),
        nullable=False,
        index=True,
    )
    store_permission_id = Column(
        UUID(as_uuid=False),
        ForeignKey("store_permissions.id"),
        nullable=False,
        index=True,
    )
    is_granted = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=text("now()"),
    )
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    created_by = Column(Text, nullable=True)
    updated_by = Column(Text, nullable=True)
