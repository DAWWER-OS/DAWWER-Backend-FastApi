import uuid
from sqlalchemy import Column, DateTime, Integer, JSON, String
from sqlalchemy.sql import func
from app.db.session import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id = Column(String, primary_key=True, default=generate_uuid, index=True)
    store_id = Column(String, nullable=False, index=True)
    filename = Column(String, nullable=False)
    status = Column(String, nullable=False, default="UPLOADED")
    total_processed = Column(Integer, nullable=False, default=0)
    valid_count = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    errors_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=True, default=func.now())
    updated_at = Column(DateTime, nullable=True, default=func.now(), onupdate=func.now())
