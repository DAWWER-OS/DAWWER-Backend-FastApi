import datetime
import uuid
import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import (
    DOTNET_EMAIL_CLAIM,
    DOTNET_NAME_IDENTIFIER_CLAIM,
    DOTNET_ROLE_CLAIM,
    verify_store_access,
    verify_token,
)
from app.db.session import SessionLocal
from app.main import app
from app.models.store import Store
from app.models.store_rbac import StoreRole, StoreStaff
from app.models.user import User

client = TestClient(app)


def create_token(
    user_id: str,
    role: str = "User",
    store_id: str | None = None,
    email: str | None = None,
    use_dotnet_claims: bool = False,
) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "exp": int((now + datetime.timedelta(hours=1)).timestamp()),
        "iat": int(now.timestamp()),
    }
    if use_dotnet_claims:
        payload[DOTNET_NAME_IDENTIFIER_CLAIM] = str(user_id)
        payload[DOTNET_ROLE_CLAIM] = role
        if email:
            payload[DOTNET_EMAIL_CLAIM] = email
        if store_id:
            payload["http://schemas.dawwer.com/identity/claims/storeid"] = str(store_id)
    else:
        payload["sub"] = str(user_id)
        payload["role"] = role
        if email:
            payload["email"] = email
        if store_id:
            payload["store_id"] = str(store_id)

    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@pytest.fixture
def owner_user():
    db = SessionLocal()
    try:
        user_id = str(uuid.uuid4())
        u = User(
            id=user_id,
            email=f"owner_{user_id[:8]}@dawer.com",
            full_name="Store Owner",
            password_hash="mock_hash",
            role="User",
            status="Active",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    finally:
        db.close()


@pytest.fixture
def other_user():
    db = SessionLocal()
    try:
        user_id = str(uuid.uuid4())
        u = User(
            id=user_id,
            email=f"other_{user_id[:8]}@dawer.com",
            full_name="Other User",
            password_hash="mock_hash",
            role="User",
            status="Active",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    finally:
        db.close()


@pytest.fixture
def admin_user():
    db = SessionLocal()
    try:
        user_id = str(uuid.uuid4())
        u = User(
            id=user_id,
            email=f"admin_{user_id[:8]}@dawer.com",
            full_name="Admin User",
            password_hash="mock_hash",
            role="Admin",
            status="Active",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    finally:
        db.close()


@pytest.fixture
def test_store(owner_user):
    db = SessionLocal()
    try:
        store_id = str(uuid.uuid4())
        s = Store(
            id=store_id,
            owner_id=owner_user.id,
            name=f"Test Store {store_id[:6]}",
            description="A test store for testing",
            city="Riyadh",
            status="APPROVED",
            verification_status="APPROVED",
            is_active=True,
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        return s
    finally:
        db.close()


def test_get_store_by_id(test_store):
    response = client.get(f"/api/v1/stores/{test_store.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_store.id
    assert data["name"] == test_store.name
    assert data["owner_id"] == test_store.owner_id
    assert data["store_id"] == test_store.id


def test_get_store_by_id_not_found():
    random_id = str(uuid.uuid4())
    response = client.get(f"/api/v1/stores/{random_id}")
    assert response.status_code == 404


def test_verify_store_access_owner(test_store, owner_user):
    token = create_token(user_id=owner_user.id, role="User")
    payload = verify_token(token)
    db = SessionLocal()
    try:
        res = verify_store_access(store_id=test_store.id, current_user=payload, db=db)
        assert res.user_id == owner_user.id
    finally:
        db.close()


def test_verify_store_access_admin(test_store, admin_user):
    token = create_token(user_id=admin_user.id, role="Admin")
    payload = verify_token(token)
    db = SessionLocal()
    try:
        res = verify_store_access(store_id=test_store.id, current_user=payload, db=db)
        assert res.user_id == admin_user.id
    finally:
        db.close()


def test_verify_store_access_token_store_id(test_store, other_user):
    token = create_token(user_id=other_user.id, role="User", store_id=test_store.id)
    payload = verify_token(token)
    db = SessionLocal()
    try:
        res = verify_store_access(store_id=test_store.id, current_user=payload, db=db)
        assert res.store_id == test_store.id
    finally:
        db.close()


def test_verify_store_access_staff(test_store, other_user):
    db = SessionLocal()
    try:
        role = db.query(StoreRole).filter(StoreRole.store_id == test_store.id).first()
        if not role:
            role = StoreRole(
                id=str(uuid.uuid4()),
                store_id=test_store.id,
                name="Store Associate",
            )
            db.add(role)
            db.commit()
            db.refresh(role)

        staff = StoreStaff(
            id=str(uuid.uuid4()),
            store_id=test_store.id,
            user_id=other_user.id,
            store_role_id=role.id,
            status="Active",
        )
        db.add(staff)
        db.commit()

        token = create_token(user_id=other_user.id, role="User")
        payload = verify_token(token)
        res = verify_store_access(store_id=test_store.id, current_user=payload, db=db)
        assert res.user_id == other_user.id
    finally:
        db.close()


def test_verify_store_access_isolation_br14_forbidden(test_store, other_user):
    token = create_token(user_id=other_user.id, role="User", store_id=str(uuid.uuid4()))
    payload = verify_token(token)
    db = SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc_info:
            verify_store_access(store_id=test_store.id, current_user=payload, db=db)
        assert exc_info.value.status_code == 403
        assert "BR-14" in exc_info.value.detail or "Operation not permitted" in exc_info.value.detail
    finally:
        db.close()


def test_dotnet_jwt_claims_parsing(test_store, owner_user):
    token = create_token(
        user_id=owner_user.id,
        role="User",
        store_id=test_store.id,
        email="owner@dotnet.com",
        use_dotnet_claims=True,
    )
    payload = verify_token(token)
    assert payload.user_id == owner_user.id
    assert payload.role == "User"
    assert payload.store_id == test_store.id
    assert payload.email == "owner@dotnet.com"
