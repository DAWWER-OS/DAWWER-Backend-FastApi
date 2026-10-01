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


def delete_shelf_image(store_id: str, image_url: Optional[str]) -> bool:
    """Safely removes an uploaded shelf image from disk within uploads/shelf_jobs/{store_id}/."""
    if not image_url:
        return False

    try:
        decoded_url = urllib.parse.unquote(image_url)
        filename = Path(decoded_url).name

        store_dir = (SHELF_UPLOADS_DIR / str(store_id)).resolve()
        file_path = (store_dir / filename).resolve()

        # Prevent directory traversal attacks
        if not str(file_path).startswith(str(store_dir)):
            logger.warning(
                "Security warning: attempted path traversal in delete_shelf_image: %s",
                image_url,
            )
            return False

        if file_path.is_file():
            file_path.unlink(missing_ok=True)
            logger.info("Deleted shelf image file: %s", file_path)
            return True

        # Also attempt direct check from repository root if relative
        direct_path = Path(decoded_url.lstrip("/")).resolve()
        if direct_path.is_file() and str(direct_path).startswith(str(store_dir)):
            direct_path.unlink(missing_ok=True)
            logger.info("Deleted shelf image file via direct path: %s", direct_path)
            return True

        logger.info("Shelf image file not found on disk, skipping removal: %s", file_path)
        return False
    except Exception as exc:
        logger.warning("Error deleting shelf image %s for store %s: %s", image_url, store_id, exc)
        return False

