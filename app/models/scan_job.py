import enum
import uuid
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class ScanJobStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class ScanJob(Base):
    __tablename__ = "scan_jobs"

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
    status = Column(
        String(32),
        nullable=False,
        default=ScanJobStatus.PENDING.value,
        server_default=text("'PENDING'"),
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=text("now()"),
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=text("now()"),
        onupdate=func.now(),
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    refunded_at = Column(DateTime(timezone=True), nullable=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True, index=True)
    lease_owner = Column(String(255), nullable=True)

    # Captures the reset boundary of the store when reserved; prevents old-period refunds from corrupting a new period
    quota_period_reset_at = Column(DateTime(timezone=True), nullable=False)

    # Machine-readable failure category and sanitized details
    failure_reason = Column(String(255), nullable=True)
    error_details = Column(Text, nullable=True)

    # Optional client-supplied idempotency key
    idempotency_key = Column(String(255), nullable=True, index=True)

    # Reference to generated shelf job (if applicable) and extraction metrics
    shelf_job_id = Column(String(64), nullable=True)
    extracted_drafts_count = Column(Integer, nullable=False, default=0, server_default=text("0"))

    # Relationship to Store
    store = relationship("Store", backref="scan_jobs")

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'REFUNDED')",
            name="ck_scan_jobs_status",
        ),
        Index("ix_scan_jobs_stale_lookup", "status", "heartbeat_at", "created_at"),
        Index("ix_scan_jobs_store_idempotency", "store_id", "idempotency_key"),
    )
