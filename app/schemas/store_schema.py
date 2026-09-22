from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


class StoreStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"


class StoreBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Name of the store")
    description: Optional[str] = Field(default=None, description="Detailed description of the store")
    commercial_registration_number: Optional[str] = Field(default=None, description="Official CR number")
    tax_number: Optional[str] = Field(default=None, description="Tax / VAT number")
    phone_number: Optional[str] = Field(default=None, description="Primary contact phone number")
    email: Optional[str] = Field(default=None, description="Store contact email")
    address: Optional[str] = Field(default=None, description="Physical street address")
    city: Optional[str] = Field(default=None, description="City name")
    latitude: Optional[float] = Field(default=None, description="Geographical latitude")
    longitude: Optional[float] = Field(default=None, description="Geographical longitude")
    logo_url: Optional[str] = Field(default=None, description="URL to store logo image")
    cover_image_url: Optional[str] = Field(default=None, description="URL to store banner cover image")


class StoreCreate(StoreBase):
    pass


class StoreUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    commercial_registration_number: Optional[str] = None
    tax_number: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    logo_url: Optional[str] = None
    cover_image_url: Optional[str] = None


class StoreStatusUpdate(BaseModel):
    status: str = Field(..., description="Target status: APPROVED, REJECTED, SUSPENDED, PENDING")
    rejection_reason: Optional[str] = Field(default=None, description="Reason if rejected")
    suspension_reason: Optional[str] = Field(default=None, description="Reason if suspended")
    information_request_message: Optional[str] = Field(default=None, description="Message requesting additional info")

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_upper = v.upper()
            if v_upper in ("APPROVED", "REJECTED", "SUSPENDED", "PENDING"):
                return v_upper
        return v


class StoreResponse(StoreBase):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    owner_id: str
    status: str = "PENDING"
    verification_status: Optional[str] = "APPROVED"
    rejection_reason: Optional[str] = None
    information_request_message: Optional[str] = None
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by_id: Optional[str] = None
    approved_at: Optional[datetime] = None
    suspended_at: Optional[datetime] = None
    suspension_reason: Optional[str] = None
    is_active: Optional[bool] = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    @computed_field
    @property
    def store_id(self) -> str:
        """Alias property so clients can access either response.id or response.store_id."""
        return self.id


# Aliases for naming convention consistency across routers and services
StoreSchema = StoreResponse
StoreCreateSchema = StoreCreate
StoreUpdateSchema = StoreUpdate
StoreResponseSchema = StoreResponse
StoreStatusUpdateSchema = StoreStatusUpdate
