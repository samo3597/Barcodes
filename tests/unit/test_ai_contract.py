"""Strict AI output validation tests."""

import pytest
from pydantic import ValidationError

from packages.contracts import AIProductResult


def valid_result() -> dict[str, object]:
    return {
        "barcode": "4850000000007",
        "name": {"value": "Demo", "confidence": 0.9},
        "atg_code": {"value": "0403", "confidence": 0.8},
        "vat": {"value": True, "confidence": 0.7},
        "is_weighted": {"value": False, "confidence": 1.0},
        "category_id": {"value": "dairy.sour_cream", "confidence": 0.95},
        "warnings": [],
    }


def test_ai_result_requires_strict_boolean_and_four_digit_atg() -> None:
    payload = valid_result()
    payload["vat"] = {"value": 1, "confidence": 0.7}
    with pytest.raises(ValidationError):
        AIProductResult.model_validate(payload)

    payload = valid_result()
    payload["atg_code"] = {"value": "403", "confidence": 0.8}
    with pytest.raises(ValidationError):
        AIProductResult.model_validate(payload)


def test_ai_result_rejects_unknown_category_slug_characters() -> None:
    payload = valid_result()
    payload["category_id"] = {"value": "Կաթնամթերք", "confidence": 0.8}

    with pytest.raises(ValidationError):
        AIProductResult.model_validate(payload)
