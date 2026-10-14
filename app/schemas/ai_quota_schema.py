from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class AIQuotaResponseSchema(BaseModel):
    store_id: str
    scans_used: int = Field(ge=0, description="Total number of scans used in the current period")
    scans_limit: int = Field(ge=0, description="Maximum scans allowed per 30-day period")
    scans_remaining: int = Field(ge=0, description="Remaining scans available (limit - used)")
    resets_at: datetime = Field(description="UTC timestamp when the current 30-day quota period resets")

    model_config = ConfigDict(from_attributes=True)


class ScanJobAcceptedResponseSchema(BaseModel):
    job_id: str
    store_id: str
    status: str
    created_at: datetime
    message: str = "Scan job accepted for processing"
    idempotency_key: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
