"""Stores endpoint backward-compatibility module re-exporting from app.routers.store_router."""

from app.routers.store_router import router

__all__ = ["router"]
