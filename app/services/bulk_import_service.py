from typing import Any, Dict
from sqlalchemy.orm import Session

from app.models.import_job import ImportJob
from app.models.product import StoreProduct


def create_import_job(db: Session, store_id: str, filename: str) -> ImportJob:
    job = ImportJob(
        store_id=store_id,
        filename=filename,
        status="UPLOADED",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def save_bulk_import_results(
    db: Session, job_id: str, store_id: str, summary_data: Dict[str, Any]
) -> ImportJob:
    job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
    if not job:
        raise ValueError(f"ImportJob with id '{job_id}' not found")

    valid_records = summary_data.get("valid_records", [])
    products = []
    for record in valid_records:
        data = (
            record.model_dump(mode="json")
            if hasattr(record, "model_dump")
            else dict(record)
        )
        product = StoreProduct(store_id=store_id, **data)
        products.append(product)

    if products:
        db.add_all(products)

    total_processed = summary_data.get("total_processed", 0)
    valid_count = summary_data.get("valid_count", 0)
    error_count = summary_data.get("error_count", 0)

    errors_list = []
    for err in summary_data.get("errors", []):
        if hasattr(err, "model_dump"):
            errors_list.append(err.model_dump(mode="json"))
        elif isinstance(err, dict):
            errors_list.append(err)
        else:
            errors_list.append(str(err))

    if error_count == 0:
        status = "COMPLETED"
    elif valid_count > 0:
        status = "COMPLETED_WITH_ERRORS"
    else:
        status = "FAILED"

    job.total_processed = total_processed
    job.valid_count = valid_count
    job.error_count = error_count
    job.errors_json = errors_list
    job.status = status

    db.commit()
    db.refresh(job)
    return job
