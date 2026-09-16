from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, field_validator


class StoreStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class StoreBase(BaseModel):
    name: str
    description: Optional[str] = None


class StoreCreate(StoreBase):
    pass


class StoreStatusUpdate(BaseModel):
    status: Literal["APPROVED", "REJECTED"]

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_upper = v.upper()
            if v_upper in ("APPROVED", "REJECTED"):
                return v_upper
        return v


class StoreResponse(StoreBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    status: str
    is_active: bool
    created_at: Optional[datetime] = None

