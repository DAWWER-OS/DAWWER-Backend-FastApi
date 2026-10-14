import io
import logging
from typing import Set, Tuple
from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger("daweros_api.image_validation")

# Strict 10 MiB limit
MAX_IMAGE_SIZE_BYTES: int = 10 * 1024 * 1024
CHUNK_SIZE: int = 64 * 1024  # 64 KiB chunks for bounded memory streaming

ALLOWED_MIME_TYPES: Set[str] = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


def detect_magic_signature(data: bytes) -> str | None:
    """Detects actual image format by inspecting magic bytes signature."""
    if len(data) < 12:
        return None
    # JPEG: FF D8 FF
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    # WebP: RIFF ???? WEBP
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def validate_image_upload(file: UploadFile) -> Tuple[bytes, str]:
    """Reads and strictly validates an uploaded image before acquiring locks or reserving quota.

    Enforces:
    1. Bounded chunked streaming read (max 10 MiB).
    2. Non-empty file validation.
    3. Magic signature detection (rejects spoofed MIME headers).
    4. Image integrity check via Pillow (detects corruption/truncation).
    5. Permitted formats: JPEG, PNG, WebP only.

    Returns:
        (image_bytes, validated_mime_type)

    Raises:
        HTTPException(400) if validation fails.
    """
    # 1. Preliminary content-type check if supplied
    if file.content_type and file.content_type.lower() not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image type '{file.content_type}'. Allowed types: image/jpeg, image/png, image/webp",
        )

    # 2. Bounded streaming read to protect server memory against oversized uploads
    total_bytes = bytearray()
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total_bytes.extend(chunk)
        if len(total_bytes) > MAX_IMAGE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File exceeds maximum allowed size of 10 MiB ({MAX_IMAGE_SIZE_BYTES} bytes)",
            )

    raw_bytes = bytes(total_bytes)

    # 3. Check for empty payload
    if len(raw_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes)",
        )

    # 4. Strict magic byte signature verification (ignore untrusted client headers)
    detected_mime = detect_magic_signature(raw_bytes)
    if not detected_mime or detected_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content does not match a valid JPEG, PNG, or WebP image signature",
        )

    # 5. Image integrity and truncation check via Pillow
    try:
        with Image.open(io.BytesIO(raw_bytes)) as img:
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        logger.warning("Corrupted or malformed image rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploaded image is malformed or corrupted: {str(exc)}",
        )

    return raw_bytes, detected_mime
