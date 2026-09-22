"""Gemini AI Vision and extraction service (app.ai module)."""

from app.services.gemini_service import (
    analyze_shelf_image,
    get_gemini_client,
)

__all__ = ["analyze_shelf_image", "get_gemini_client"]
