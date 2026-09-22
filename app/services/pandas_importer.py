import difflib
import io
import uuid
from typing import Any, Dict, List
import pandas as pd
from pydantic import ValidationError

from app.schemas.import_schema import RowValidationError
from app.schemas.product_schema import ProductCreateSchema

COLUMN_MAPPING: Dict[str, List[str]] = {
    "product_name": ["product_name", "اسم المنتج", "اسم الصنف", "المنتج", "الصنف", "Name", "Product Name"],
    "price": ["price", "سعر البيع", "سعر بيع", "السعر", "سعر الصنف", "Price"],
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

MANDATORY_COLUMNS: List[str] = [
    "product_name",
    "price",
]

MANDATORY_COLUMN_NAMES_AR: Dict[str, str] = {
    "product_name": "اسم المنتج",
    "price": "السعر",
    "store_sku": "رمز الصنف (SKU)",
    "category": "الفئة",
    "zone": "المنطقة",
    "aisle": "الممر",
    "map_target": "الموقع على الخريطة",
}


def normalize_header(header: str) -> str:
    return header.strip().lower().replace("_", "").replace("-", "").replace(" ", "")


SYNONYM_LOOKUP: Dict[str, str] = {}
for standard_key, synonyms in COLUMN_MAPPING.items():
    SYNONYM_LOOKUP[normalize_header(standard_key)] = standard_key
    for syn in synonyms:
        SYNONYM_LOOKUP[normalize_header(syn)] = standard_key


def process_bulk_catalog_file(file_bytes: bytes, filename: str) -> Dict[str, Any]:
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
        raise ValueError("Unsupported file format. Please upload a .csv or .xlsx file.")

    df.columns = df.columns.astype(str).str.strip()

    rename_map = {}
    all_lookup_keys = list(SYNONYM_LOOKUP.keys())
    for col in df.columns:
        norm = normalize_header(col)
        if norm in SYNONYM_LOOKUP:
            rename_map[col] = SYNONYM_LOOKUP[norm]
            continue
        close = difflib.get_close_matches(norm, all_lookup_keys, n=1, cutoff=0.75)
        if close:
            rename_map[col] = SYNONYM_LOOKUP[close[0]]

    df.rename(columns=rename_map, inplace=True)

    missing = [col for col in MANDATORY_COLUMNS if col not in df.columns]
    if missing:
        missing_labels = [f"{MANDATORY_COLUMN_NAMES_AR.get(col, col)} ({col})" for col in missing]
        raise ValueError(f"الملف لا يحتوي على الأعمدة الإلزامية التالية: {', '.join(missing_labels)}")

    valid_records = []
    errors = []

    records = df.to_dict(orient="records")

    for row_number, raw_row in enumerate(records, start=2):
        row_data = {}
        for key, value in raw_row.items():
            if key not in COLUMN_MAPPING:
                continue
            if pd.isna(value):
                row_data[key] = None
            elif isinstance(value, float) and value.is_integer():
                row_data[key] = int(value)
            else:
                row_data[key] = value

        string_fields = (
            "store_sku", "barcode", "product_name", "category",
            "zone", "aisle", "rack", "shelf", "map_target"
        )
        for field in string_fields:
            if field in row_data and row_data[field] is not None:
                row_data[field] = str(row_data[field]).strip()

        if not row_data.get("store_sku"):
            barcode = row_data.get("barcode")
            if barcode:
                row_data["store_sku"] = f"SKU-{barcode}"
            else:
                row_data["store_sku"] = f"SKU-{uuid.uuid4().hex[:8].upper()}"

        if not row_data.get("category"):
            row_data["category"] = "عام"

        if not row_data.get("zone"):
            row_data["zone"] = "Zone 1"

        if not row_data.get("aisle"):
            row_data["aisle"] = "Aisle 1"

        if not row_data.get("map_target"):
            row_data["map_target"] = "Target 1"

        if not row_data.get("shelf"):
            row_data["shelf"] = "A1"

        if row_data.get("quantity") is None:
            row_data["quantity"] = 0

        sku = row_data.get("store_sku")

        try:
            validated_row = ProductCreateSchema(**row_data)
            valid_records.append(validated_row)
        except ValidationError as e:
            error_messages = [
                f"{err['loc'][0] if err.get('loc') else 'field'}: {err['msg']}"
                for err in e.errors()
            ]
            errors.append(
                RowValidationError(
                    row_number=row_number,
                    sku=sku,
                    error_messages=error_messages,
                )
            )

    return {
        "total_processed": len(records),
        "valid_count": len(valid_records),
        "error_count": len(errors),
        "valid_records": valid_records,
        "errors": errors,
    }
