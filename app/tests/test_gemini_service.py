import json
from unittest.mock import MagicMock, patch
import pytest

from app.services.gemini_service import analyze_shelf_image


def test_analyze_shelf_image_strips_markdown_and_applies_defaults(caplog):
    mock_raw_response_text = """```json
[
  {
    "proposed_name": "حليب المراعي 2 لتر",
    "category_hint": "ألبان",
    "confidence_score": 0.95
  },
  {
    "name": "عصير راني برتقال",
    "estimated_price": 4.5,
    "barcode_detected": "628100123456"
  }
]
```"""

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = mock_raw_response_text
    mock_client.models.generate_content.return_value = mock_response

    with patch("app.services.gemini_service.get_gemini_client", return_value=mock_client):
        with caplog.at_level("INFO"):
            results = analyze_shelf_image(b"\xff\xd8\xffdummy_image_bytes")

    assert len(results) == 2

    # Check item 1 defaults: missing price -> 0.0, missing barcode -> ""
    assert results[0].proposed_name == "حليب المراعي 2 لتر"
    assert results[0].estimated_price == 0.0
    assert results[0].barcode_detected == ""
    assert results[0].confidence_score == 0.95

    # Check item 2: proposed_name inferred from name, price and barcode preserved
    assert results[1].proposed_name == "عصير راني برتقال"
    assert results[1].estimated_price == 4.5
    assert results[1].barcode_detected == "628100123456"

    # Verify detailed logging of raw response text
    assert "Raw Gemini API response" in caplog.text
    assert "حليب المراعي 2 لتر" in caplog.text


def test_analyze_shelf_image_handles_empty_response(caplog):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "[]"
    mock_client.models.generate_content.return_value = mock_response

    with patch("app.services.gemini_service.get_gemini_client", return_value=mock_client):
        with caplog.at_level("WARNING"):
            results = analyze_shelf_image(b"\xff\xd8\xffdummy_image_bytes")

    assert results == []
    assert "Gemini response parsed into an empty product array" in caplog.text
