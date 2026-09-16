from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    role: Optional[str] = None
    created_at: Optional[datetime] = None


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
