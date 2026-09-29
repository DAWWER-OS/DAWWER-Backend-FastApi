from typing import List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, verify_store_access
from app.schemas.analytics_schema import (
    SearchLogCreateSchema,
    SearchLogResponseSchema,
    SearchTermAggregateSchema,
)
from app.services.analytics_service import (
    get_no_result_searches,
    get_top_searched_terms,
    log_search_event,
)

router = APIRouter(
    prefix="/api/v1/stores/{store_id}/analytics",
    tags=["Store Analytics"],
)


@router.post(
    "/search-logs",
    response_model=SearchLogResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Log customer search query event",
    description="Records customer search query activity, timestamp, and product result count for discovery insights.",
)
def create_search_log(
    store_id: str,
    payload: SearchLogCreateSchema,
    db: Session = Depends(get_db),
) -> SearchLogResponseSchema:
    log_dict = log_search_event(
        db=db,
        store_id=store_id,
        query_text=payload.query_text,
        result_count=payload.result_count,
    )
    return SearchLogResponseSchema(**log_dict)


@router.get(
    "/top-searches",
    response_model=List[SearchTermAggregateSchema],
    status_code=status.HTTP_200_OK,
    summary="Get top searched terms for store",
    description="Merchant endpoint (BR-14) returning the most frequent search keywords and frequency counts.",
)
def read_top_searches(
    store_id: str,
    limit: int = Query(default=10, ge=1, le=100, description="Max number of top terms to return"),
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> List[SearchTermAggregateSchema]:
    results = get_top_searched_terms(db=db, store_id=store_id, limit=limit)
    return [SearchTermAggregateSchema(**r) for r in results]


@router.get(
    "/no-results",
    response_model=List[SearchTermAggregateSchema],
    status_code=status.HTTP_200_OK,
    summary="Get high-demand zero-result missing product searches",
    description="Merchant endpoint (BR-14) returning search terms that yielded zero product results for inventory expansion insights.",
)
def read_no_result_searches(
    store_id: str,
    limit: int = Query(default=10, ge=1, le=100, description="Max number of missing product terms to return"),
    db: Session = Depends(get_db),
    current_user=Depends(verify_store_access),
) -> List[SearchTermAggregateSchema]:
    results = get_no_result_searches(db=db, store_id=store_id, limit=limit)
    return [SearchTermAggregateSchema(**r) for r in results]
