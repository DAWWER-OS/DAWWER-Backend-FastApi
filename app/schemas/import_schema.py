from typing import List, Optional
from pydantic import BaseModel

from app.schemas.product_schema import ProductCreateSchema, StockStatusEnum

CatalogImportRowSchema = ProductCreateSchema


class RowValidationError(BaseModel):
    row_number: int
    sku: Optional[str] = None
    error_messages: List[str]


class BulkImportSummaryResponse(BaseModel):
    job_id: str
    store_id: str
    filename: str
    total_processed: int
    valid_count: int
    error_count: int
    valid_records: List[ProductCreateSchema]
    errors: List[RowValidationError]
