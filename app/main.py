import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.exceptions import setup_exception_handlers
from app.core.logging import setup_logging
from app.db.session import Base, engine
import app.models
from app.routers import (
    draft_product_router,
    health_router,
    product_router,
    shelf_job_router,
    store_router,
)
from app.schemas.response import ErrorResponseModel

setup_logging()

try:
    Base.metadata.create_all(bind=engine, checkfirst=True)
except Exception as exc:
    logging.getLogger(__name__).warning("create_all note: %s", exc)

# OpenAPI tags documentation definitions for clean Swagger UI presentation
TAGS_METADATA = [
    {
        "name": "System Health",
        "description": "Liveness and database connectivity probes for infrastructure monitoring.",
    },
    {
        "name": "Stores & JWT Security Dependencies",
        "description": "Store profile retrieval and BR-14 store isolation scoping dependency.",
    },
    {
        "name": "Products & Catalog Bulk Import",
        "description": "Store inventory catalog management, manual CRUD operations, and CSV/Excel bulk imports.",
    },
    {
        "name": "Shelf Jobs & Gemini AI Capture",
        "description": "Physical shelf capture jobs, image uploads, and multimodal Gemini AI product extraction.",
    },
    {
        "name": "AI Draft Approvals & Review",
        "description": "Merchant review, field correction, single approval, batch approval, and rejection of AI drafts.",
    },
]

app = FastAPI(
    title="DAWEROS Backend API",
    description="Production API for DAWEROS platform with AI shelf vision and store catalog management.",
    version="1.0.0",
    openapi_tags=TAGS_METADATA,
    responses={
        400: {"model": ErrorResponseModel, "description": "Bad Request"},
        401: {"model": ErrorResponseModel, "description": "Unauthorized"},
        403: {"model": ErrorResponseModel, "description": "Forbidden"},
        404: {"model": ErrorResponseModel, "description": "Not Found"},
        422: {"model": ErrorResponseModel, "description": "Validation Error"},
        500: {"model": ErrorResponseModel, "description": "Internal Server Error"},
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

setup_exception_handlers(app)

# Ensure uploads directory exists and mount static files route for uploaded shelf images
uploads_dir = Path("uploads")
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Health & Production Routers
app.include_router(health_router.router)
app.include_router(store_router.router)
app.include_router(product_router.router)
app.include_router(shelf_job_router.router)
app.include_router(draft_product_router.router)

