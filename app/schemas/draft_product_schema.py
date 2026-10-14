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


class ProductDraftJobDetailsResponseSchema(BaseModel):
    """Detailed response schema for a product draft extraction job, supporting Merchant Dashboard warnings."""
    id: str
    job_id: str
    jobId: Optional[str] = None
    store_id: str
    storeId: Optional[str] = None
    status: str = "REVIEW_REQUIRED"
    products_count: int = 0
    productsCount: int = 0
    has_warning: bool = False
    hasWarning: bool = False
    warning_code: Optional[str] = None
    warningCode: Optional[str] = None
    user_message: Optional[str] = None
    userMessage: Optional[str] = None
    warning: Optional[str] = None
    message: Optional[str] = None
    products: List[DraftProductResponseSchema] = []
    metadata: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @classmethod
    def sync_data(cls, data: dict) -> dict:
        if "jobId" in data and "job_id" not in data:
            data["job_id"] = data["jobId"]
        elif "job_id" in data and "jobId" not in data:
            data["jobId"] = data["job_id"]
        if "storeId" in data and "store_id" not in data:
            data["store_id"] = data["storeId"]
        elif "store_id" in data and "storeId" not in data:
            data["storeId"] = data["store_id"]
        if "productsCount" in data and "products_count" not in data:
            data["products_count"] = data["productsCount"]
        elif "products_count" in data and "productsCount" not in data:
            data["productsCount"] = data["products_count"]
        if "hasWarning" in data and "has_warning" not in data:
            data["has_warning"] = data["hasWarning"]
        elif "has_warning" in data and "hasWarning" not in data:
            data["hasWarning"] = data["has_warning"]
        if "warningCode" in data and "warning_code" not in data:
            data["warning_code"] = data["warningCode"]
        elif "warning_code" in data and "warningCode" not in data:
            data["warningCode"] = data["warning_code"]
        if "userMessage" in data and "user_message" not in data:
            data["user_message"] = data["userMessage"]
        elif "user_message" in data and "userMessage" not in data:
            data["userMessage"] = data["user_message"]
        if data.get("warning") is None and data.get("warning_code"):
            data["warning"] = data.get("warning_code")
        return data
