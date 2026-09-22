from datetime import datetime, timezone
from typing import List, Optional, Union
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.models.store import Store
from app.schemas.store_schema import StoreCreate, StoreStatus, StoreUpdate


def get_active_stores(
    db: Session,
    skip: int = 0,
    limit: int = 20,
) -> List[Store]:
    """Retrieve all approved and active stores with pagination."""
    return (
        db.query(Store)
        .filter(Store.status == "APPROVED", Store.is_active.is_(True))
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_store_by_id(
    db: Session,
    store_id: str,
) -> Optional[Store]:
    """Retrieve a single store by its ID."""
    return db.query(Store).filter(Store.id == store_id).first()


def get_stores_by_owner(
    db: Session,
    owner_id: str,
    skip: int = 0,
    limit: int = 20,
) -> List[Store]:
    """Retrieve all stores owned by a specific user."""
    return (
        db.query(Store)
        .filter(Store.owner_id == owner_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def create_store(
    db: Session,
    owner_id: str,
    data: Union[StoreCreate, dict],
) -> Store:
    """Create a new store record associated with the given owner_id."""
    if hasattr(data, "model_dump"):
        store_data = data.model_dump(exclude_unset=True)
    elif isinstance(data, dict):
        store_data = data.copy()
    else:
        raise ValueError("Invalid store creation payload")

    store = Store(
        owner_id=owner_id,
        status="PENDING",
        verification_status="APPROVED",
        is_active=True,
        submitted_at=datetime.now(timezone.utc),
        **store_data,
    )
    try:
        db.add(store)
        db.commit()
        db.refresh(store)
        return store
    except Exception:
        db.rollback()
        raise


def update_store(
    db: Session,
    store_id: str,
    data: Union[StoreUpdate, dict],
) -> Store:
    """Update profile and location attributes of an existing store."""
    store = get_store_by_id(db, store_id)
    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store with id '{store_id}' not found",
        )

    if hasattr(data, "model_dump"):
        update_data = data.model_dump(exclude_unset=True)
    elif isinstance(data, dict):
        update_data = data.copy()
    else:
        raise ValueError("Invalid store update payload")

    for field, value in update_data.items():
        if hasattr(store, field):
            setattr(store, field, value)

    store.updated_at = func.now()

    try:
        db.commit()
        db.refresh(store)
        return store
    except Exception:
        db.rollback()
        raise


def get_pending_stores(
    db: Session,
    skip: int = 0,
    limit: int = 20,
) -> List[Store]:
    """Retrieve all stores currently pending administrative review."""
    return (
        db.query(Store)
        .filter(Store.status == "PENDING")
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_store_status(
    db: Session,
    store_id: str,
    new_status: Union[str, StoreStatus],
    rejection_reason: Optional[str] = None,
    suspension_reason: Optional[str] = None,
    information_request_message: Optional[str] = None,
    reviewed_by_id: Optional[str] = None,
) -> Store:
    """Update administrative moderation status for a store."""
    store = get_store_by_id(db, store_id)
    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store with id '{store_id}' not found",
        )

    status_val = new_status.value if hasattr(new_status, "value") else str(new_status)
    status_upper = status_val.upper()
    valid_statuses = ("APPROVED", "REJECTED", "SUSPENDED", "PENDING")
    if status_upper not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{new_status}'. Allowed statuses are {valid_statuses}.",
        )

    store.status = status_upper
    store.reviewed_at = func.now()

    if reviewed_by_id:
        store.reviewed_by_id = reviewed_by_id

    if status_upper == "APPROVED":
        store.approved_at = func.now()
        store.rejection_reason = None
        store.suspension_reason = None
    elif status_upper == "REJECTED":
        store.rejection_reason = rejection_reason
    elif status_upper == "SUSPENDED":
        store.suspended_at = func.now()
        store.suspension_reason = suspension_reason

    if information_request_message is not None:
        store.information_request_message = information_request_message

    try:
        db.commit()
        db.refresh(store)
        return store
    except Exception:
        db.rollback()
        raise


def deactivate_store(
    db: Session,
    store_id: str,
) -> Store:
    """Soft delete/deactivate a store."""
    store = get_store_by_id(db, store_id)
    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store with id '{store_id}' not found",
        )
    store.is_active = False
    store.updated_at = func.now()
    try:
        db.commit()
        db.refresh(store)
        return store
    except Exception:
        db.rollback()
        raise
