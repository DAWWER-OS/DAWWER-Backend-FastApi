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


def test_analyze_shelf_image_structured_success():
    mock_raw = json.dumps({
        "status": "SUCCESS",
        "message": "تم استخراج المنتجات بنجاح",
        "products": [
            {
                "proposed_name": "شيبس ليز بالملح",
                "estimated_price": 2.5,
                "category_hint": "سناكات",
                "pack_size": "50 جم",
                "barcode_detected": "12345678",
                "confidence_score": 0.92,
            }
        ]
    })
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = mock_raw
    mock_client.models.generate_content.return_value = mock_response

    with patch("app.services.gemini_service.get_gemini_client", return_value=mock_client):
        result = analyze_shelf_image(b"\xff\xd8\xffimage")

    assert result.status == "SUCCESS"
    assert result.has_warning is False
    assert result.warning_code is None
    assert len(result.products) == 1
    assert result.products[0].proposed_name == "شيبس ليز بالملح"
    assert result[0].proposed_name == "شيبس ليز بالملح"


def test_analyze_shelf_image_structured_no_products_detected(caplog):
    mock_raw = json.dumps({
        "status": "NO_PRODUCTS_DETECTED",
        "message": "لم يتم التعرف على أي منتجات تجارية في الصورة",
        "products": []
    })
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = mock_raw
    mock_client.models.generate_content.return_value = mock_response

    with patch("app.services.gemini_service.get_gemini_client", return_value=mock_client):
        with caplog.at_level("WARNING"):
            result = analyze_shelf_image(b"\xff\xd8\xffimage")

    assert result.status == "NO_PRODUCTS_DETECTED"
    assert result.has_warning is True
    assert result.warning_code == "NO_PRODUCTS_FOUND"
    assert len(result) == 0
    assert result.products == []
    assert result == []
    assert "NO_PRODUCTS_DETECTED" in caplog.text
