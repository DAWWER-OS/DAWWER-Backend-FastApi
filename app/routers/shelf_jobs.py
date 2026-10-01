"""Shelf jobs router module re-exporting from shelf_job_router for backward compatibility."""

from app.routers.shelf_job_router import (
    create_shelf_job,
    delete_shelf_job,
    delete_shelf_job_legacy,
    delete_shelf_job_legacy_store_path,
    get_shelf_job,
    get_shelf_job_legacy,
    legacy_router,
    list_store_shelf_jobs,
    router,
)

__all__ = [
    "router",
    "legacy_router",
    "create_shelf_job",
    "get_shelf_job",
    "list_store_shelf_jobs",
    "delete_shelf_job",
    "delete_shelf_job_legacy_store_path",
    "delete_shelf_job_legacy",
    "get_shelf_job_legacy",
]
