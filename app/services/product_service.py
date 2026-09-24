import difflib
import io
import uuid
from typing import Any, Dict, List, Optional
import pandas as pd
from pydantic import ValidationError
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.models.product import ProductLocation, StoreProduct
from app.schemas.product_schema import ProductCreateSchema, ProductUpdateSchema

COLUMN_MAPPING: Dict[str, List[str]] = {
    "product_name": ["product_name", "اسم المنتج", "اسم الصنف", "المنتج", "الصنف", "Name", "Product Name"],
    "price": ["price", "سعر البيع", "السعر", "سعر الصنف", "Price"],
    "store_sku": ["store_sku", "sku", "كود الصنف", "رمز الصنف", "رمز المنتج", "الرمز", "SKU"],
    "barcode": ["barcode", "الباركود", "باركود", "رقم الباركود", "Barcode"],
    "category": ["category", "الفئة", "القسم", "التصنيف", "المجموعة", "Category"],
    "zone": ["zone", "المنطقة", "الزون", "القسم الميداني", "Zone"],
    "aisle": ["aisle", "الممر", "ممر", "Aisle"],
    "rack": ["rack", "الرف", "ستند", "Rack"],
    "shelf": ["shelf", "المستوى", "الطبقة", "Shelf"],
    "map_target": ["map_target", "الموقع على الخريطة", "الهدف", "Map Target"],
    "quantity": ["quantity", "الكمية", "المخزون", "العدد", "Quantity"],
}


def create_product(
    db: Session, store_id: str, product_in: ProductCreateSchema
) -> StoreProduct:
    existing_product = (
        db.query(StoreProduct)
        .filter(
            StoreProduct.store_id == store_id,
            StoreProduct.store_sku == product_in.store_sku,
        )
        .first()
    )
    if existing_product:
        raise ValueError("Product with this store_sku already exists in this store.")

    product = StoreProduct(
        store_id=store_id,
        **product_in.model_dump(),
    )   
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def update_product(
    db: Session,
    store_id: str,
    product_id: str,
    product_in: ProductUpdateSchema,
) -> Optional[StoreProduct]:
    product = get_product_by_id(db, store_id=store_id, product_id=product_id)
    if not product:
        return None

    update_data = product_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)
    return product


def get_product_by_id(
    db: Session, store_id: str, product_id: str
) -> Optional[StoreProduct]:
    return (
        db.query(StoreProduct)
        .filter(
            StoreProduct.id == product_id,
            StoreProduct.store_id == store_id,
        )
        .first()
    )


def delete_product(
    db: Session,
    store_id: str,
    product_id: str,
    hard_delete: bool = False,
) -> tuple[bool, Optional[StoreProduct]]:
    """Deletes or deactivates a product and updates associated location records.

    Enforces:
    - BR-14: Store isolation check (raises PermissionError if product exists in another store).
    - BR-15: Soft deactivation (is_active = False) by default, or hard delete if hard_delete=True.
    - Cascades is_active = False to associated ProductLocation records.

    Returns:
    - (is_hard_deleted: bool, product: Optional[StoreProduct])
    - Returns (False, None) if product is not found in database.
    - Raises PermissionError if product belongs to another store.
    """
    product = db.query(StoreProduct).filter(StoreProduct.id == product_id).first()
    if not product:
        return False, None

    if str(product.store_id) != str(store_id):
        raise PermissionError("Operation not permitted: Product belongs to another store")

    if hard_delete:
        db.query(ProductLocation).filter(
            ProductLocation.product_id == product_id,
            ProductLocation.store_id == store_id,
        ).delete(synchronize_session=False)

        db.delete(product)
        db.commit()
        return True, None
    else:
        product.is_active = False
        product.updated_at = func.now()

        db.query(ProductLocation).filter(
            ProductLocation.product_id == product_id,
            ProductLocation.store_id == store_id,
        ).update({"is_active": False}, synchronize_session=False)

        db.commit()
        db.refresh(product)
        return False, product


def get_store_products(
    db: Session, store_id: str, skip: int = 0, limit: int = 100
) -> List[StoreProduct]:
    return (
        db.query(StoreProduct)
        .filter(StoreProduct.store_id == store_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def bulk_upload_products(
    db: Session,
    store_id: str,
    file_bytes: Optional[bytes] = None,
    filename: Optional[str] = None,
    df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    if df is None:
        if not file_bytes or not filename:
            raise ValueError("الملف غير متوفر")
        file_buffer = io.BytesIO(file_bytes)
        filename_lower = filename.lower()
        if filename_lower.endswith(".csv"):
            try:
                df = pd.read_csv(file_buffer, encoding="utf-8")
            except UnicodeDecodeError:
                file_buffer.seek(0)
                df = pd.read_csv(file_buffer, encoding="utf-8-sig")
        elif filename_lower.endswith((".xlsx", ".xls")):
            df = pd.read_excel(file_buffer)
        else:
            raise ValueError("صيغة الملف غير مدعومة. يرجى رفع ملف بصيغة .csv أو .xlsx")

    df.columns = df.columns.astype(str).str.strip()

    synonym_to_field: Dict[str, str] = {}
    all_synonyms: List[str] = []
    for field, synonyms in COLUMN_MAPPING.items():
        for syn in synonyms:
            std_syn = syn.strip().lower()
            synonym_to_field[std_syn] = field
            if std_syn not in all_synonyms:
                all_synonyms.append(std_syn)

    rename_map = {}
    for col in df.columns:
        clean_col = str(col).strip().lower()
        if clean_col in synonym_to_field:
            rename_map[col] = synonym_to_field[clean_col]
            continue

        close_matches = difflib.get_close_matches(clean_col, all_synonyms, n=1, cutoff=0.75)
        if close_matches:
            rename_map[col] = synonym_to_field[close_matches[0]]

    df = df.rename(columns=rename_map)

    valid_products: List[ProductCreateSchema] = []
    failed_rows_details: List[Dict[str, Any]] = []

    existing_skus = set(
        s[0]
        for s in db.query(StoreProduct.store_sku)
        .filter(StoreProduct.store_id == store_id)
        .all()
    )
    seen_skus = set(existing_skus)

    for row_index, raw_row in enumerate(df.to_dict(orient="records")):
        row_number = row_index + 2
        row_dict: Dict[str, Any] = {
            k: None if pd.isna(v) or v == "" else v for k, v in raw_row.items()
        }

        sku = row_dict.get("store_sku")
        if not sku:
            barcode = row_dict.get("barcode")
            if barcode:
                sku_clean = f"SKU-{str(barcode).strip()}"
            else:
                sku_clean = f"SKU-{uuid.uuid4().hex[:8].upper()}"
        else:
            sku_clean = str(sku).strip()

        if sku_clean in seen_skus:
            if sku:
                failed_rows_details.append({"row": row_number, "error": f"رمز الصنف '{sku_clean}' مكرر"})
                continue
            else:
                sku_clean = f"{sku_clean}-{uuid.uuid4().hex[:4].upper()}"

        row_dict["store_sku"] = sku_clean
        seen_skus.add(sku_clean)

        product_name = row_dict.get("product_name")
        if not product_name or not str(product_name).strip():
            failed_rows_details.append({"row": row_number, "error": "اسم المنتج مفقود"})
            continue
        row_dict["product_name"] = str(product_name).strip()

        raw_price = row_dict.get("price")
        if raw_price is None or (isinstance(raw_price, str) and not raw_price.strip()):
            failed_rows_details.append({"row": row_number, "error": "السعر غير صالح"})
            continue
        try:
            price = float(raw_price)
            if price < 0:
                failed_rows_details.append({"row": row_number, "error": "السعر غير صالح"})
                continue
            row_dict["price"] = price
        except (ValueError, TypeError):
            failed_rows_details.append({"row": row_number, "error": "السعر غير صالح"})
            continue

        raw_qty = row_dict.get("quantity")
        if raw_qty is None or (isinstance(raw_qty, str) and not raw_qty.strip()):
            row_dict["quantity"] = 0
        else:
            try:
                row_dict["quantity"] = int(float(raw_qty))
            except (ValueError, TypeError):
                row_dict["quantity"] = 0

        raw_shelf = row_dict.get("shelf")
        row_dict["shelf"] = str(raw_shelf).strip() if raw_shelf else "A1"

        raw_rack = row_dict.get("rack")
        row_dict["rack"] = str(raw_rack).strip() if raw_rack else None

        raw_barcode = row_dict.get("barcode")
        row_dict["barcode"] = str(raw_barcode).strip() if raw_barcode else None

        row_dict["category"] = str(row_dict.get("category") or "عام").strip()
        row_dict["zone"] = str(row_dict.get("zone") or "Zone 1").strip()
        row_dict["aisle"] = str(row_dict.get("aisle") or "Aisle 1").strip()
        row_dict["map_target"] = str(row_dict.get("map_target") or "Target 1").strip()

        try:
            product_obj = ProductCreateSchema(**row_dict)
            valid_products.append(product_obj)
            seen_skus.add(sku_clean)
        except ValidationError as exc:
            failed_rows_details.append({"row": row_number, "error": f"بيانات غير صالحة: {exc.errors()[0]['msg']}"})

    db_products = [
        StoreProduct(store_id=store_id, **p.model_dump())
        for p in valid_products
    ]
    if db_products:
        db.add_all(db_products)
        db.commit()

    return {
        "total_rows": len(df),
        "successful_count": len(db_products),
        "failed_count": len(failed_rows_details),
        "failed_rows_details": failed_rows_details,
    }
