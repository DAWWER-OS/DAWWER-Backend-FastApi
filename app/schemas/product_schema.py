from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class StockStatusEnum(str, Enum):
    IN_STOCK = "IN_STOCK"
    LOW_STOCK = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"


class ProductCreateSchema(BaseModel):
    store_sku: str
    barcode: Optional[str] = None
    product_name: str
    category: str
    price: float = Field(..., ge=0.0, description="Price must be non-negative")
    stock_status: StockStatusEnum = StockStatusEnum.IN_STOCK
    quantity: Optional[int] = Field(default=0, ge=0)
    zone: str
    aisle: str
    rack: Optional[str] = None
    shelf: Optional[str] = None
    map_target: str


class ProductUpdateSchema(BaseModel):
    store_sku: Optional[str] = None
    barcode: Optional[str] = None
    product_name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = Field(default=None, ge=0.0, description="Price must be non-negative")
    stock_status: Optional[StockStatusEnum] = None
    quantity: Optional[int] = Field(default=None, ge=0)
    zone: Optional[str] = None
    aisle: Optional[str] = None
    rack: Optional[str] = None
    shelf: Optional[str] = None
    map_target: Optional[str] = None


class ProductResponseSchema(ProductCreateSchema):
    id: str
    store_id: str
    is_active: bool = True
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ProductDeleteResponseSchema(BaseModel):
    message: str = "Product successfully deactivated"
    product_id: str
    store_id: str
    deleted: bool = True
    is_active: bool
    hard_deleted: bool = False
    product: Optional[ProductResponseSchema] = None

    model_config = ConfigDict(from_attributes=True)
