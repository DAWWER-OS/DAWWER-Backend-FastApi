from typing import Any, Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.analytics import SearchLog


def log_search_event(
    db: Session,
    store_id: str,
    query_text: str,
    result_count: int,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Records customer search query string, timestamp, and resulting product count."""
    cleaned_query = (query_text or "").strip()
    is_no_result = (result_count == 0)

    log_entry = SearchLog(
        store_id=str(store_id),
        user_id=str(user_id) if user_id else None,
        query_text=cleaned_query,
        result_count=max(0, result_count),
        is_no_result=is_no_result,
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)

    return {
        "id": str(log_entry.id),
        "store_id": str(log_entry.store_id),
        "user_id": log_entry.user_id,
        "query_text": log_entry.query_text,
        "result_count": log_entry.result_count,
        "is_no_result": log_entry.is_no_result,
        "created_at": log_entry.created_at,
    }


def get_top_searched_terms(
    db: Session,
    store_id: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Aggregates most frequent search keywords for a store."""
    results = (
        db.query(
            SearchLog.query_text,
            func.count(SearchLog.id).label("count"),
        )
        .filter(SearchLog.store_id == str(store_id))
        .group_by(SearchLog.query_text)
        .order_by(func.count(SearchLog.id).desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "query_text": r[0],
            "count": int(r[1]),
        }
        for r in results
    ]


def get_no_result_searches(
    db: Session,
    store_id: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Aggregates search terms that yielded zero product results (is_no_result = True)."""
    results = (
        db.query(
            SearchLog.query_text,
            func.count(SearchLog.id).label("count"),
        )
        .filter(
            SearchLog.store_id == str(store_id),
            SearchLog.is_no_result.is_(True),
        )
        .group_by(SearchLog.query_text)
        .order_by(func.count(SearchLog.id).desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "query_text": r[0],
            "count": int(r[1]),
        }
        for r in results
    ]
