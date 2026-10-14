import json
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class GeminiExtractionResult(BaseModel):
    """Structured extraction result returned by Gemini Vision API."""
    status: str = "SUCCESS"  # "SUCCESS" | "NO_PRODUCTS_DETECTED"
    products: List[ExtractedDraftProductSchema] = []
    message: Optional[str] = None
    has_warning: bool = False
    warning_code: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __iter__(self):
        return iter(self.products)

    def __len__(self):
        return len(self.products)

    def __getitem__(self, index):
        return self.products[index]

    def __bool__(self):
        return bool(self.products)

    def __eq__(self, other):
        if isinstance(other, list):
            return self.products == other
        return super().__eq__(other)


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
    products_count: int = 0
    productsCount: int = 0
    has_warning: bool = False
    hasWarning: bool = False
    warning_code: Optional[str] = None
    warningCode: Optional[str] = None
    user_message: Optional[str] = None
    userMessage: Optional[str] = None
    warning: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def populate_warnings_and_counts(cls, data: Any) -> Any:
        if hasattr(data, "__dict__"):
            # SQLAlchemy model or class instance
            extracted_count = getattr(data, "extracted_drafts_count", 0)
            err_msg = getattr(data, "error_message", None)
            stat = getattr(data, "status", None)
            stat_str = str(stat.value if hasattr(stat, "value") else stat)

            has_warn = False
            warn_code = None
            u_msg = None

            if err_msg:
                try:
                    meta = json.loads(err_msg)
                    if isinstance(meta, dict):
                        has_warn = meta.get("has_warning", False) or "warning" in meta or "warning_code" in meta
                        warn_code = meta.get("warning_code") or meta.get("warning") or meta.get("code")
                        u_msg = meta.get("user_message") or meta.get("message")
                except Exception:
                    if "NO_PRODUCTS_FOUND" in err_msg:
                        has_warn = True
                        warn_code = "NO_PRODUCTS_FOUND"
                        u_msg = "لم يتعرف النظام على أي منتجات تجارية في هذه الصورة. يرجى التأكد من توجيه الكاميرا لرف حقيقي ومضاء جيداً."

            if extracted_count == 0 and stat_str == "REVIEW_REQUIRED":
                has_warn = True
                warn_code = warn_code or "NO_PRODUCTS_FOUND"
                u_msg = u_msg or "لم يتعرف النظام على أي منتجات تجارية في هذه الصورة. يرجى التأكد من توجيه الكاميرا لرف حقيقي ومضاء جيداً."

            # Construct dictionary for schema validation
            data_dict = {
                "id": str(getattr(data, "id", "")),
                "store_id": str(getattr(data, "store_id", "")),
                "status": stat_str,
                "zone": getattr(data, "zone", "A"),
                "aisle": getattr(data, "aisle", "1"),
                "rack": getattr(data, "rack", None),
                "shelf": getattr(data, "shelf", None),
                "image_url": getattr(data, "image_url", None),
                "extracted_drafts_count": extracted_count,
                "products_count": extracted_count,
                "productsCount": extracted_count,
                "has_warning": has_warn,
                "hasWarning": has_warn,
                "warning_code": warn_code,
                "warningCode": warn_code,
                "user_message": u_msg,
                "userMessage": u_msg,
                "warning": warn_code,
                "error_message": err_msg,
                "created_at": getattr(data, "created_at", None),
                "updated_at": getattr(data, "updated_at", None),
            }
            return data_dict
        elif isinstance(data, dict):
            # Dict input
            count = data.get("extracted_drafts_count", data.get("products_count", data.get("productsCount", 0)))
            data["products_count"] = count
            data["productsCount"] = count
            if data.get("hasWarning") is not None and "has_warning" not in data:
                data["has_warning"] = data["hasWarning"]
            elif data.get("has_warning") is not None and "hasWarning" not in data:
                data["hasWarning"] = data["has_warning"]
            if data.get("warningCode") and not data.get("warning_code"):
                data["warning_code"] = data["warningCode"]
            elif data.get("warning_code") and not data.get("warningCode"):
                data["warningCode"] = data["warning_code"]
            if data.get("userMessage") and not data.get("user_message"):
                data["user_message"] = data["userMessage"]
            elif data.get("user_message") and not data.get("userMessage"):
                data["userMessage"] = data["user_message"]
        return data


class ShelfJobDeleteResponseSchema(BaseModel):
    message: str = "Shelf job successfully deleted"
    job_id: str
    id: Optional[str] = None
    product_id: Optional[str] = None
    store_id: str
    deleted: bool = True

