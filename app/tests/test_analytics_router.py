import datetime
import uuid
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.analytics import SearchLog
from app.models.store import Store
from app.models.user import User

client = TestClient(app)


def create_token(user_id: str, role: str = "User", store_id: str | None = None) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "exp": int((now + datetime.timedelta(hours=1)).timestamp()),
        "iat": int(now.timestamp()),
    }
    if store_id:
        payload["store_id"] = str(store_id)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def test_analytics_stores(db: Session):
    """Sets up two clean test stores for analytics aggregation and BR-14 tenant isolation tests."""
    user_a = User(
        id=str(uuid.uuid4()),
        email=f"analytics_owner_a_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Analytics Owner A",
        role="StoreOwner",
        password_hash="test_hash",
    )
    user_b = User(
        id=str(uuid.uuid4()),
        email=f"analytics_owner_b_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Analytics Owner B",
        role="StoreOwner",
        password_hash="test_hash",
    )
    db.add_all([user_a, user_b])
    db.commit()

    store_a = Store(
        id=str(uuid.uuid4()),
        name=f"Analytics Store A {uuid.uuid4().hex[:4]}",
        owner_id=str(user_a.id),
        status="APPROVED",
        verification_status="APPROVED",
        is_active=True,
    )
    store_b = Store(
        id=str(uuid.uuid4()),
        name=f"Analytics Store B {uuid.uuid4().hex[:4]}",
        owner_id=str(user_b.id),
        status="APPROVED",
        verification_status="APPROVED",
        is_active=True,
    )
    db.add_all([store_a, store_b])
    db.commit()

    context = {
        "user_a": user_a,
        "user_b": user_b,
        "store_a": store_a,
        "store_b": store_b,
        "token_a": create_token(user_id=str(user_a.id), store_id=str(store_a.id)),
        "token_b": create_token(user_id=str(user_b.id), store_id=str(store_b.id)),
    }

    yield context

    # Cleanup
    db.query(SearchLog).filter(SearchLog.store_id.in_([store_a.id, store_b.id])).delete(synchronize_session=False)
    db.query(Store).filter(Store.id.in_([store_a.id, store_b.id])).delete(synchronize_session=False)
    db.query(User).filter(User.id.in_([user_a.id, user_b.id])).delete(synchronize_session=False)
    db.commit()


def test_post_search_logs_success(test_analytics_stores):
    """Verifies POST /search-logs records valid customer search events."""
    store_a = test_analytics_stores["store_a"]

    payload = {
        "query_text": "Organic Milk 1L",
        "result_count": 5,
    }

    response = client.post(
        f"/api/v1/stores/{store_a.id}/analytics/search-logs",
        json=payload,
    )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["store_id"] == str(store_a.id)
    assert data["query_text"] == "Organic Milk 1L"
    assert data["result_count"] == 5
    assert data["is_no_result"] is False


def test_get_top_searches_aggregation(test_analytics_stores):
    """Verifies GET /top-searches returns top aggregated keywords with frequency counts."""
    store_a = test_analytics_stores["store_a"]
    token_a = test_analytics_stores["token_a"]
    headers = {"Authorization": f"Bearer {token_a}"}

    # Log several searches
    for _ in range(3):
        client.post(
            f"/api/v1/stores/{store_a.id}/analytics/search-logs",
            json={"query_text": "Chocolate Chip Cookies", "result_count": 12},
        )
    for _ in range(2):
        client.post(
            f"/api/v1/stores/{store_a.id}/analytics/search-logs",
            json={"query_text": "Greek Yogurt", "result_count": 4},
        )

    response = client.get(
        f"/api/v1/stores/{store_a.id}/analytics/top-searches?limit=10",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    assert data[0]["query_text"] == "Chocolate Chip Cookies"
    assert data[0]["count"] >= 3
    assert data[1]["query_text"] == "Greek Yogurt"
    assert data[1]["count"] >= 2


def test_get_no_results_searches(test_analytics_stores):
    """Verifies GET /no-results correctly captures zero-result search terms for missing product discovery."""
    store_a = test_analytics_stores["store_a"]
    token_a = test_analytics_stores["token_a"]
    headers = {"Authorization": f"Bearer {token_a}"}

    # Log zero-result searches
    for _ in range(4):
        client.post(
            f"/api/v1/stores/{store_a.id}/analytics/search-logs",
            json={"query_text": "Gluten Free Pita Bread", "result_count": 0},
        )

    response = client.get(
        f"/api/v1/stores/{store_a.id}/analytics/no-results?limit=10",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["query_text"] == "Gluten Free Pita Bread"
    assert data[0]["count"] >= 4


def test_analytics_store_isolation_br14_forbidden(test_analytics_stores):
    """Verifies store isolation (BR-14) prevents a store owner from accessing another store's analytics."""
    store_a = test_analytics_stores["store_a"]
    token_b = test_analytics_stores["token_b"]  # Owner B's token
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Owner B attempts to view Store A's top searches
    top_resp = client.get(
        f"/api/v1/stores/{store_a.id}/analytics/top-searches",
        headers=headers_b,
    )
    assert top_resp.status_code == 403

    # Owner B attempts to view Store A's no-results searches
    no_result_resp = client.get(
        f"/api/v1/stores/{store_a.id}/analytics/no-results",
        headers=headers_b,
    )
    assert no_result_resp.status_code == 403
