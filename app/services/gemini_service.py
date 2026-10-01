import json
import logging
import os
import re
import sys
import traceback
from typing import List
from google import genai
from google.genai import types

from app.core.config import settings
from app.schemas.shelf_job_schema import ExtractedDraftProductSchema

logger = logging.getLogger("daweros_api.gemini")

PRIMARY_MODEL = "gemini-2.5-flash"
FALLBACK_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-3.1-flash-lite-preview",
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
        "You are an expert retail computer vision assistant specializing in supermarket inventory and shelf inspection "
        "in Arabic and Palestinian retail store contexts.\n\n"
        "Analyze this retail shelf photo and detect all visible distinct commercial retail products on the shelf.\n"
        "For each detected product, extract its details and return a valid JSON array of objects with the following schema:\n"
        "[\n"
        "  {\n"
        '    "proposed_name": "اسم المنتج الشائع بالعربية (مثال: حليب المراعي 2 لتر، جبنة كيري، شيبس شيبسي بالملح)",\n'
        '    "estimated_price": 0.0,\n'
        '    "category_hint": "الفئة (مثل: ألبان وأجبان، مشروبات وعصائر، سناكات وشوكولاتة، منظفات، مواد غذائية)",\n'
        '    "pack_size": "حجم العبوة إن وجد (مثل: 500 مل، 1 كغم، 250 جم، أو نص فارغ \"\")",\n'
        '    "barcode_detected": "الباركود إن كان ظاهراً ومقروءاً على العبوة أو بطاقة الرف، وإلا نص فارغ \"\"",\n'
        '    "confidence_score": 0.90\n'
        "  }\n"
        "]\n\n"
        "Rules & Guidelines:\n"
        "1. Detect every clearly visible product brand and packaging on the shelves.\n"
        "2. Provide 'proposed_name' in Arabic as commonly called in local Palestinian/Arab grocery stores (or include English brand if prominent).\n"
        "3. If a price tag is visible near or under the product, extract 'estimated_price' as a float; if no price is visible, use 0.0 as default.\n"
        "4. If barcode is visible and legible, extract it into 'barcode_detected'; otherwise assign an empty string \"\".\n"
        "5. If no products are visible at all, or the photo is completely blank/unrelated, return an empty array [].\n"
        "6. Return ONLY the JSON array. Do not include markdown code block formatting (such as ```json) or explanatory text."
    )

    models_to_try = [PRIMARY_MODEL] + [m for m in FALLBACK_MODELS if m != PRIMARY_MODEL]
    last_error: Exception | None = None
    response = None
    selected_model = None

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
                selected_model = model_name
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

    # Detailed logging of raw response text for diagnostic purposes
    logger.info("Raw Gemini API response from model '%s' (length: %d chars):\n%s", selected_model, len(response.text), response.text)

    # Robust stripping of markdown code blocks (```json ... ``` or ``` ... ```)
    raw_text = response.text.strip()
    if "```" in raw_text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text, re.IGNORECASE)
        if match:
            raw_text = match.group(1).strip()
        else:
            lines = raw_text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw_text = "\n".join(lines).strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        err_detail = f"Failed to parse Gemini response as JSON: {exc}. Raw text: {raw_text[:300]}"
        logger.error("%s\n%s", err_detail, traceback.format_exc())
        print(f"\n[GEMINI PARSE ERROR] {err_detail}\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        raise ValueError(err_detail)

    if not isinstance(data, list):
        # In case model returned a single dictionary wrapping a list e.g. {"products": [...]}
        if isinstance(data, dict):
            for key in ("products", "items", "detected_products", "data", "draft_products"):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
            else:
                data = [data]
        else:
            raise ValueError("Gemini output must be a JSON array of products")

    if len(data) == 0:
        logger.warning(
            "Gemini response parsed into an empty product array []. Model: '%s'. Raw response was:\n%s",
            selected_model,
            response.text,
        )

    draft_products = []
    for item in data:
        if isinstance(item, dict):
            # Ensure required proposed_name has a fallback if missing
            if not item.get("proposed_name"):
                item["proposed_name"] = item.get("name") or item.get("title") or "منتج غير محدد"

            # Default missing or invalid prices to 0.0
            if item.get("estimated_price") is None:
                item["estimated_price"] = 0.0
            else:
                try:
                    item["estimated_price"] = float(item["estimated_price"])
                except (ValueError, TypeError):
                    item["estimated_price"] = 0.0

            # Default missing or None barcodes to empty string ""
            if not item.get("barcode_detected"):
                item["barcode_detected"] = ""
            else:
                item["barcode_detected"] = str(item["barcode_detected"]).strip()

            # Default pack_size and category_hint
            if item.get("pack_size") is None:
                item["pack_size"] = ""
            if item.get("category_hint") is None:
                item["category_hint"] = "عام"

            # Default confidence_score between 0.0 and 1.0
            if item.get("confidence_score") is None:
                item["confidence_score"] = 0.85
            else:
                try:
                    item["confidence_score"] = max(0.0, min(1.0, float(item["confidence_score"])))
                except (ValueError, TypeError):
                    item["confidence_score"] = 0.85

            draft_products.append(ExtractedDraftProductSchema(**item))

    logger.info("Successfully extracted %d draft products from shelf image using model '%s'", len(draft_products), selected_model)
    return draft_products
