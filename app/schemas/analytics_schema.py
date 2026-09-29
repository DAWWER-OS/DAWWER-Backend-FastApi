from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class SearchLogCreateSchema(BaseModel):
    query_text: str = Field(..., min_length=1, description="Customer search query string")
    result_count: int = Field(..., ge=0, description="Number of matching products returned")


class SearchLogResponseSchema(BaseModel):
    id: str
    store_id: str
    user_id: Optional[str] = None
    query_text: str
    result_count: int
    is_no_result: bool
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SearchTermAggregateSchema(BaseModel):
    query_text: str = Field(..., description="Search keyword query text")
    count: int = Field(..., ge=0, description="Total occurrences / frequency count")

    model_config = ConfigDict(from_attributes=True)
