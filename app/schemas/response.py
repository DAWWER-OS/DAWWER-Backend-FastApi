from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class ResponseModel(BaseModel, Generic[T]):
    success: bool = True
    message: str = "Operation completed successfully"
    data: Optional[T] = None


class ErrorResponseModel(BaseModel):
    success: bool = False
    error_code: str
    message: str
    details: Optional[Any] = None
