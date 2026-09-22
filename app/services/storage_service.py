import logging
import os
from pathlib import Path
import re
from typing import Optional, Tuple
import urllib.parse
import uuid

logger = logging.getLogger("daweros_api.storage")

UPLOADS_DIR = Path("uploads")
SHELF_UPLOADS_DIR = UPLOADS_DIR / "shelf_jobs"


def ensure_upload_dirs() -> None:
    SHELF_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_filename(raw_filename: Optional[str]) -> str:
    """Safely decodes and cleans filename while preserving Arabic and Unicode characters."""
    if not raw_filename:
        return "shelf_image.jpg"

    # 1. Decode percent-encoding if client sent %D8%B5...
    try:
        decoded = urllib.parse.unquote(raw_filename)
    except Exception:
        decoded = raw_filename

    # 2. Fix potential latin-1 mojibake if UTF-8 was received as latin-1
    try:
        reencoded = decoded.encode("latin-1").decode("utf-8")
        if any("\u0600" <= c <= "\u06ff" for c in reencoded):
            decoded = reencoded
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    path = Path(decoded)
    stem = path.stem.strip()
    suffix = path.suffix.lower()
    if suffix not in [".jpg", ".jpeg", ".png", ".webp"]:
        suffix = ".jpg"

    # Strip dangerous filesystem characters while preserving Arabic/alphanumeric
    cleaned_stem = re.sub(r'[\\/*?:"<>|]', "", stem).strip()
    if not cleaned_stem:
        cleaned_stem = "shelf_capture"

    return f"{cleaned_stem}{suffix}"


def save_shelf_image(
    store_id: str, raw_filename: Optional[str], image_bytes: bytes
) -> Tuple[str, str]:
    """Saves the uploaded shelf image to disk and returns (file_path, public_image_url).

    Correctly preserves Arabic file names and guarantees an accessible public URL.
    """
    ensure_upload_dirs()
    store_dir = SHELF_UPLOADS_DIR / str(store_id)
    store_dir.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_filename(raw_filename)
    unique_prefix = uuid.uuid4().hex[:8]
    unique_filename = f"{unique_prefix}_{safe_name}"

    file_path = store_dir / unique_filename
    with open(file_path, "wb") as f:
        f.write(image_bytes)

    # URL-encode the filename component in image_url for standard HTTP transport
    url_filename = urllib.parse.quote(unique_filename)
    public_url = f"/uploads/shelf_jobs/{store_id}/{url_filename}"
    logger.info("Saved shelf image for store %s to %s (URL: %s)", store_id, file_path, public_url)
    return str(file_path), public_url
