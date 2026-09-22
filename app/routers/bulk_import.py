"""Bulk import router re-exporting from product_router for backward compatibility."""

from app.routers.product_router import bulk_import_catalog, router

__all__ = ["router", "bulk_import_catalog"]
