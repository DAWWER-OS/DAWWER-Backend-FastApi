import uuid
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.session import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class StoreDocument(Base):
    __tablename__ = "store_documents"

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
    document_type = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    original_file_name = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    file_size = Column(BigInteger, nullable=False)
    storage_path = Column(String, nullable=False)
    uploaded_by_id = Column(UUID(as_uuid=False), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=text("now()"),
    )
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    created_by = Column(Text, nullable=True)
    updated_by = Column(Text, nullable=True)
