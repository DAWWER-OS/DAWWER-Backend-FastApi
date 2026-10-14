import datetime
import io
import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.import_job import ImportJob
from app.models.product import StoreProduct
from app.models.store import Store

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
def store():
    db = SessionLocal()
    try:
        s = db.query(Store).first()
        if not s:
            from app.models.user import User
            import uuid
            u = db.query(User).first()
            if not u:
                u = User(
                    id=str(uuid.uuid4()),
                    email="test_owner@dawer.com",
                    full_name="Test Owner",
                    role="User",
                )
                db.add(u)
                db.commit()
                db.refresh(u)
            s = Store(
                id=str(uuid.uuid4()),
                name="Test Store",
                owner_id=str(u.id),
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


@pytest.fixture(autouse=True)
def cleanup():
    yield
    db = SessionLocal()
    try:
        db.query(StoreProduct).filter(
            StoreProduct.store_sku.in_(["SKU-101", "SKU-102", "SKU-201", "SKU-301"])
        ).delete()
        db.query(ImportJob).filter(
            ImportJob.filename.in_(["catalog.csv", "catalog_mixed.csv", "catalog.txt"])
        ).delete()
        db.commit()
    finally:
        db.close()


def test_bulk_import_success(store):
    token = create_token(user_id=store.owner_id, store_id=store.id)
    csv_content = (
        "store_sku,product_name,category,price,zone,aisle,map_target\n"
        "SKU-101,Keyboard,Electronics,29.99,Zone A,Aisle 1,Node 1\n"
        "SKU-102,Mouse,Electronics,14.50,Zone A,Aisle 2,Node 2\n"
    )
    files = {"file": ("catalog.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(f"/api/v1/stores/{store.id}/catalog/bulk-import", headers=headers, files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["total_processed"] == 2
    assert data["valid_count"] == 2
    assert data["error_count"] == 0
    assert len(data["valid_records"]) == 2


def test_bulk_import_partial_errors(store):
    token = create_token(user_id=store.owner_id, store_id=store.id)
    csv_content = (
        "store_sku,product_name,category,price,zone,aisle,map_target\n"
        "SKU-201,Monitor,Electronics,199.99,Zone B,Aisle 3,Node 3\n"
        "SKU-202,Broken Item,Electronics,-10.0,Zone B,Aisle 3,Node 4\n"
    )
    files = {"file": ("catalog_mixed.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(f"/api/v1/stores/{store.id}/catalog/bulk-import", headers=headers, files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["total_processed"] == 2
    assert data["valid_count"] == 1
    assert data["error_count"] == 1
    assert len(data["errors"]) == 1
    assert data["errors"][0]["row_number"] == 3
    assert len(data["errors"][0]["error_messages"]) > 0


def test_bulk_import_invalid_file_format(store):
    token = create_token(user_id=store.owner_id, store_id=store.id)
    files = {"file": ("catalog.txt", io.BytesIO(b"invalid data"), "text/plain")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(f"/api/v1/stores/{store.id}/catalog/bulk-import", headers=headers, files=files)

    assert response.status_code == 400


def test_bulk_import_store_scoping_forbidden(store):
    other_token = create_token(user_id="other_user_999", role="User", store_id="store_other_123")
    csv_content = (
        "store_sku,product_name,category,price,zone,aisle,map_target\n"
        "SKU-301,Item,Category,10.0,Zone C,Aisle 1,Node 5\n"
    )
    files = {"file": ("catalog.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    headers = {"Authorization": f"Bearer {other_token}"}

    response = client.post(f"/api/v1/stores/{store.id}/catalog/bulk-import", headers=headers, files=files)

    assert response.status_code == 403


def test_bulk_import_arabic_columns_success(store):
    token = create_token(user_id=store.owner_id, store_id=store.id)
    arabic_csv = (
        "رمز الصنف,اسم المنتج,القسم,سعر البيع,المنطقة,الممر,الموقع على الخريطة,الكمية\n"
        "SKU-AR-101,قهوة عربية,مشروبات ساخنة,35.0,المنطقة الأولى,ممر 2,TARGET-COFFEE,100\n"
    )
    files = {"file": ("catalog_ar.csv", io.BytesIO(arabic_csv.encode("utf-8")), "text/csv")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(f"/api/v1/stores/{store.id}/catalog/bulk-import", headers=headers, files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["valid_count"] == 1
    assert data["error_count"] == 0
    assert data["valid_records"][0]["product_name"] == "قهوة عربية"
    assert data["valid_records"][0]["store_sku"] == "SKU-AR-101"


def test_bulk_import_missing_mandatory_columns_error(store):
    token = create_token(user_id=store.owner_id, store_id=store.id)
    # Missing price/السعر
    incomplete_csv = (
        "رمز الصنف,اسم المنتج,القسم,المنطقة,الممر,الموقع على الخريطة\n"
        "SKU-AR-102,شاي,مشروبات ساخنة,منطقة 1,ممر 2,TARGET-TEA\n"
    )
    files = {"file": ("catalog_missing.csv", io.BytesIO(incomplete_csv.encode("utf-8")), "text/csv")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(f"/api/v1/stores/{store.id}/catalog/bulk-import", headers=headers, files=files)
    assert response.status_code == 400
    res_data = response.json()
    err_text = res_data.get("message") or res_data.get("detail") or str(res_data)
    assert "الأعمدة الإلزامية" in err_text


def test_bulk_import_excel_success(store):
    import pandas as pd
    token = create_token(user_id=store.owner_id, store_id=store.id)
    df = pd.DataFrame([
        {
            "store_sku": "SKU-XL-101",
            "product_name": "Organic Milk",
            "category": "Dairy",
            "price": 12.50,
            "zone": "Zone Cold",
            "aisle": "Aisle 4",
            "map_target": "FRIDGE-1",
            "quantity": 50,
        }
    ])
    excel_io = io.BytesIO()
    with pd.ExcelWriter(excel_io, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    excel_io.seek(0)

    files = {"file": ("catalog.xlsx", excel_io, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(f"/api/v1/stores/{store.id}/catalog/bulk-import", headers=headers, files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["valid_count"] == 1
    assert data["valid_records"][0]["product_name"] == "Organic Milk"


def test_bulk_import_token_expired(store):
    # Expired token (issued in the past with exp in the past)
    now = datetime.datetime.now(datetime.timezone.utc)
    expired_payload = {
        "sub": str(store.owner_id),
        "role": "Merchant",
        "store_id": str(store.id),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "exp": int((now - datetime.timedelta(hours=2)).timestamp()),
        "iat": int((now - datetime.timedelta(hours=3)).timestamp()),
    }
    expired_token = jwt.encode(expired_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    files = {"file": ("catalog.csv", io.BytesIO(b"product_name,price\nItem,10\n"), "text/csv")}
    headers = {"Authorization": f"Bearer {expired_token}"}

    response = client.post(f"/api/v1/stores/{store.id}/catalog/bulk-import", headers=headers, files=files)
    assert response.status_code == 401
    data = response.json()
    assert data.get("code") == "TOKEN_EXPIRED"
    assert "انتهت جلسة الدخول" in data.get("message", "")


def test_bulk_import_store_scoping_merchant_success(store):
    # Merchant with matching store_id
    merchant_token = create_token(user_id=store.owner_id, role="Merchant", store_id=store.id)
    csv_content = (
        "store_sku,product_name,category,price,zone,aisle,map_target\n"
        "SKU-M-101,Tablet,Electronics,450.0,Zone T,Aisle 1,Node 9\n"
    )
    files = {"file": ("catalog_merchant.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    headers = {"Authorization": f"Bearer {merchant_token}"}

    response = client.post(f"/api/v1/stores/{store.id}/catalog/bulk-import", headers=headers, files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["valid_count"] == 1


def test_bulk_import_store_scoping_forbidden_code(store):
    other_token = create_token(user_id="unauthorized_user_1", role="Merchant", store_id="unrelated_store_id")
    files = {"file": ("catalog.csv", io.BytesIO(b"product_name,price\nItem,10\n"), "text/csv")}
    headers = {"Authorization": f"Bearer {other_token}"}

    response = client.post(f"/api/v1/stores/{store.id}/catalog/bulk-import", headers=headers, files=files)
    assert response.status_code == 403
    data = response.json()
    assert data.get("code") == "STORE_ACCESS_DENIED"


def test_bulk_import_empty_file_problem_details(store):
    token = create_token(user_id=store.owner_id, store_id=store.id)
    files = {"file": ("empty.xlsx", io.BytesIO(b""), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(f"/api/v1/stores/{store.id}/catalog/bulk-import", headers=headers, files=files)
    assert response.status_code == 400
    data = response.json()
    assert "type" in data
    assert "title" in data
    assert "status" in data
    assert data.get("code") == "EMPTY_FILE"

