from typing import List, Union
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.store import Store
from app.schemas.store import StoreCreate, StoreStatus


def get_active_stores(
    db: Session,
    skip: int = 0,
    limit: int = 20,
) -> List[Store]:
    return (
        db.query(Store)
        .filter(Store.status == "APPROVED", Store.is_active == True)
        .offset(skip)
        .limit(limit)
        .all()
    )


def create_store(
    db: Session,
    owner_id: str,
    data: StoreCreate,
) -> Store:
    store = Store(
        name=data.name,
        description=data.description,
        owner_id=owner_id,
        status="PENDING",
        is_active=True,
    )
    try:
        db.add(store)
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
) -> Store:
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store with id '{store_id}' not found",
        )

    status_val = new_status.value if hasattr(new_status, "value") else str(new_status)
    status_upper = status_val.upper()
    if status_upper not in ("APPROVED", "REJECTED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{new_status}'. Allowed statuses are 'APPROVED' or 'REJECTED'.",
        )

    store.status = status_upper
    try:
        db.commit()
        db.refresh(store)
        return store
    except Exception:
        db.rollback()
        raise

