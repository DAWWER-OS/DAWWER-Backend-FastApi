from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.profile import router as profile_router
from app.api.v1.endpoints.stores import router as stores_router
from app.api.v1.endpoints.test_auth import router as test_auth_router
from app.core.config import settings
from app.core.exceptions import setup_exception_handlers
from app.core.logging import setup_logging
from app.db.session import Base, engine
import app.models
from app.schemas.response import ErrorResponseModel

setup_logging()

Base.metadata.create_all(bind=engine, checkfirst=True)

app = FastAPI(
    title="DAWEROS Backend API",
    version="1.0.0",
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

app.include_router(health_router, prefix="/api/v1")
app.include_router(health_router)
app.include_router(test_auth_router, prefix="/api/v1")
app.include_router(profile_router, prefix="/api/v1")
app.include_router(stores_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1/admin")

