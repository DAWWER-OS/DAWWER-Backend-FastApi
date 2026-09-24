import json
import logging
import os
import sys
import traceback
from typing import List
from google import genai
from google.genai import types

from app.core.config import settings
from app.schemas.shelf_job_schema import ExtractedDraftProductSchema

logger = logging.getLogger("daweros_api.gemini")

PRIMARY_MODEL = "gemini-3-flash-preview"
FALLBACK_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.6-flash",
    "gemini-flash-latest",
]


def get_gemini_client() -> genai.Client:
    api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
    if not api_key:
        err_msg = "GEMINI_API_KEY is not configured in settings (.env) or environment variables."
        logger.error(err_msg)
        print(f"\n[GEMINI CONFIG ERROR] {err_msg}", file=sys.stderr, flush=True)
        raise ValueError(err_msg)

    # Strip surrounding quotes and whitespace if present
    api_key_clean = str(api_key).strip().strip('"').strip("'")
    return genai.Client(api_key=api_key_clean)


def analyze_shelf_image(image_bytes: bytes) -> List[ExtractedDraftProductSchema]:
    if not image_bytes:
        raise ValueError("No image data provided")

    client = get_gemini_client()

    mime_type = "image/jpeg"
    if image_bytes.startswith(b"\x89PNG"):
        mime_type = "image/png"
    elif image_bytes.startswith(b"RIFF") and b"WEBP" in image_bytes[:16]:
        mime_type = "image/webp"

    prompt = (
        "You are an expert retail computer vision system specializing in shelf inventory extraction.\n"
        "Analyze this retail store shelf image and detect each visible product item on the shelf.\n"
        "Return ONLY a JSON array with objects matching:\n"
        '{"proposed_name": str, "estimated_price": float, "category_hint": str, "pack_size": str, "barcode_detected": str, "confidence_score": float}\n'
        "If a price tag is visible near the product, extract the estimated_price as float (otherwise 0.0).\n"
        "If no products are visible or image is blank/irrelevant, return an empty array [].\n"
        "confidence_score must be a float between 0.0 and 1.0."
    )

    models_to_try = [PRIMARY_MODEL] + [m for m in FALLBACK_MODELS if m != PRIMARY_MODEL]
    last_error: Exception | None = None
    response = None

    for model_name in models_to_try:
        try:
            logger.info("Sending shelf image to Gemini model '%s' (%d bytes, %s)", model_name, len(image_bytes), mime_type)
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            if response and response.text:
                break
        except Exception as exc:
            last_error = exc
            logger.warning("Gemini model '%s' failed: %s", model_name, exc)
            print(
                f"\n[GEMINI WARNING] Model '{model_name}' failed: {exc}\n{traceback.format_exc()}",
                file=sys.stderr,
                flush=True,
            )

    if not response or not response.text:
        err_detail = f"Gemini API call failed across all models {models_to_try}: {last_error}"
        logger.error("%s\n%s", err_detail, traceback.format_exc())
        print(f"\n[GEMINI API ERROR] {err_detail}\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        raise ValueError(err_detail)

    raw_text = response.text.strip()
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw_text = "\n".join(lines).strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        err_detail = f"Failed to parse Gemini response as JSON: {exc}. Raw text: {raw_text[:200]}"
        logger.error("%s\n%s", err_detail, traceback.format_exc())
        print(f"\n[GEMINI PARSE ERROR] {err_detail}\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        raise ValueError(err_detail)

    if not isinstance(data, list):
        # In case model returned a single dictionary wrapping a list e.g. {"products": [...]}
        if isinstance(data, dict):
            for key in ("products", "items", "detected_products", "data"):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
            else:
                data = [data]
        else:
            raise ValueError("Gemini output must be a JSON array of products")

    draft_products = []
    for item in data:
        if isinstance(item, dict):
            # Ensure required proposed_name has a fallback if missing
            if not item.get("proposed_name"):
                item["proposed_name"] = item.get("name") or item.get("title") or "منتج غير محدد"
            draft_products.append(ExtractedDraftProductSchema(**item))

    logger.info("Successfully extracted %d draft products from shelf image", len(draft_products))
    return draft_products
