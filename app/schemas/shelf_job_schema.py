from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class JobStatusEnum(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ShelfJobCreateSchema(BaseModel):
    zone: str
    aisle: str
    rack: Optional[str] = None
    shelf: Optional[str] = None


class ExtractedDraftProductSchema(BaseModel):
    proposed_name: str
    estimated_price: Optional[float] = Field(default=0.0, ge=0.0)
    category_hint: Optional[str] = None
    pack_size: Optional[str] = None
    barcode_detected: Optional[str] = None
    confidence_score: Optional[float] = Field(default=0.0, ge=0.0, le=1.0)


class ShelfJobResponseSchema(BaseModel):
    id: str
    store_id: str
    status: JobStatusEnum
    zone: str
    aisle: str
    rack: Optional[str] = None
    shelf: Optional[str] = None
    image_url: Optional[str] = None
    extracted_drafts_count: int = 0
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
