from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DraftProductStatusEnum(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class DraftProductResponseSchema(BaseModel):
    id: str
    store_id: str
    shelf_job_id: str
    proposed_name: str
    estimated_price: float = 0.0
    category_hint: Optional[str] = None
    pack_size: Optional[str] = None
    barcode_detected: Optional[str] = None
    confidence_score: float = 0.0
    zone: Optional[str] = None
    aisle: Optional[str] = None
    rack: Optional[str] = None
    shelf: Optional[str] = None
    status: str = "PENDING_REVIEW"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DraftProductUpdateSchema(BaseModel):
    proposed_name: Optional[str] = Field(default=None, min_length=1)
    estimated_price: Optional[float] = Field(default=None, ge=0.0)
    category_hint: Optional[str] = None
    pack_size: Optional[str] = None
    barcode_detected: Optional[str] = None
    zone: Optional[str] = None
    aisle: Optional[str] = None
    rack: Optional[str] = None
    shelf: Optional[str] = None


class DraftProductBatchApproveSchema(BaseModel):
    draft_ids: List[str] = Field(..., min_length=1, description="List of draft product IDs to approve")


class DraftProductApprovalResponseSchema(BaseModel):
    draft_id: str
    status: str
    store_product_id: Optional[str] = None
    message: str
    deleted: Optional[bool] = None
    product_id: Optional[str] = None


class DraftProductDeleteResponseSchema(BaseModel):
    message: str = "Draft product item successfully deleted"
    draft_id: str
    product_id: str
    store_id: str
    deleted: bool = True
    hard_deleted: bool = True
