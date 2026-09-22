from app.routers.draft_product_router import router as draft_product_api_router
from app.routers.health_router import router as health_api_router
from app.routers.product_router import router as product_api_router
from app.routers.shelf_job_router import router as shelf_job_api_router
from app.routers.store_router import router as store_api_router

__all__ = [
    "store_api_router",
    "product_api_router",
    "shelf_job_api_router",
    "draft_product_api_router",
    "health_api_router",
]
