from app.schemas.category import CategoryBase, CategoryCreate, CategoryResponse
from app.schemas.draft_product_schema import (
    DraftProductApprovalResponseSchema,
    DraftProductBatchApproveSchema,
    DraftProductResponseSchema,
    DraftProductStatusEnum,
    DraftProductUpdateSchema,
)
from app.schemas.import_schema import (
    BulkImportSummaryResponse,
    CatalogImportRowSchema,
    RowValidationError,
)
from app.schemas.map_schemas import (
    MapEdgeBase,
    MapEdgeCreate,
    MapEdgeResponse,
    MapEdgeSchema,
    MapEdgeUpdate,
    MapNodeBase,
    MapNodeCreate,
    MapNodeResponse,
    MapNodeSchema,
    MapNodeUpdate,
    NavigationRouteRequestSchema,
    NavigationRouteResponseSchema,
    NavigationStepSchema,
    StoreMapBase,
    StoreMapCreate,
    StoreMapResponse,
    StoreMapSchema,
    StoreMapUpdate,
)
from app.schemas.product_schema import (
    ProductCreateSchema,
    ProductDeleteResponseSchema,
    ProductResponseSchema,
    ProductUpdateSchema,
    StockStatusEnum,
)
from app.schemas.response import ErrorResponseModel, ResponseModel
from app.schemas.shelf_job_schema import (
    ExtractedDraftProductSchema,
    JobStatusEnum,
    ShelfJobCreateSchema,
    ShelfJobResponseSchema,
)
from app.schemas.store_schema import (
    StoreBase,
    StoreCreate,
    StoreCreateSchema,
    StoreResponse,
    StoreResponseSchema,
    StoreSchema,
    StoreStatus,
    StoreStatusUpdate,
    StoreStatusUpdateSchema,
    StoreUpdate,
    StoreUpdateSchema,
)
from app.schemas.token import TokenPayload
from app.schemas.user import UserProfileResponse, UserProfileUpdate

__all__ = [
    # Map & Navigation Schemas
    "MapNodeBase",
    "MapNodeCreate",
    "MapNodeUpdate",
    "MapNodeResponse",
    "MapNodeSchema",
    "MapEdgeBase",
    "MapEdgeCreate",
    "MapEdgeUpdate",
    "MapEdgeResponse",
    "MapEdgeSchema",
    "StoreMapBase",
    "StoreMapCreate",
    "StoreMapUpdate",
    "StoreMapResponse",
    "StoreMapSchema",
    "NavigationRouteRequestSchema",
    "NavigationStepSchema",
    "NavigationRouteResponseSchema",
    # Store Schemas
    "StoreBase",
    "StoreCreate",
    "StoreUpdate",
    "StoreStatusUpdate",
    "StoreResponse",
    "StoreSchema",
    "StoreCreateSchema",
    "StoreUpdateSchema",
    "StoreResponseSchema",
    "StoreStatusUpdateSchema",
    "StoreStatus",
    # Product Schemas
    "StockStatusEnum",
    "ProductCreateSchema",
    "ProductUpdateSchema",
    "ProductResponseSchema",
    "ProductDeleteResponseSchema",
    # Category Schemas
    "CategoryBase",
    "CategoryCreate",
    "CategoryResponse",
    # Import & Shelf Job Schemas
    "CatalogImportRowSchema",
    "RowValidationError",
    "BulkImportSummaryResponse",
    "JobStatusEnum",
    "ShelfJobCreateSchema",
    "ExtractedDraftProductSchema",
    "ShelfJobResponseSchema",
    "DraftProductStatusEnum",
    "DraftProductResponseSchema",
    "DraftProductUpdateSchema",
    "DraftProductBatchApproveSchema",
    "DraftProductApprovalResponseSchema",
    # General / User / Token
    "ResponseModel",
    "ErrorResponseModel",
    "TokenPayload",
    "UserProfileResponse",
    "UserProfileUpdate",
]
