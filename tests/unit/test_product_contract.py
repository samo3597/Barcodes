"""Unit tests for the public product contract."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from packages.contracts.product import PublicProduct


def product_payload() -> dict[str, object]:
    return {
        "barcode": "04850000000005",
        "name": "Թթվասեր 20% 800 գ",
        "image_url": None,
        "atg_code": "0403",
        "vat": True,
        "is_weighted": False,
        "category_id": "dairy.sour_cream",
        "version": 1,
        "quality_status": "ai_processed",
        "updated_at": datetime.now(UTC),
    }


def test_product_preserves_leading_zero_in_barcode() -> None:
    product = PublicProduct.model_validate(product_payload())

    assert product.barcode == "04850000000005"


@pytest.mark.parametrize("field", ["vat", "is_weighted"])
@pytest.mark.parametrize("invalid_value", [1, 0, "true", "false"])
def test_product_rejects_non_boolean_values(field: str, invalid_value: object) -> None:
    payload = product_payload()
    payload[field] = invalid_value

    with pytest.raises(ValidationError):
        PublicProduct.model_validate(payload)


def test_product_rejects_unknown_fields() -> None:
    payload = product_payload()
    payload["unexpected"] = "value"

    with pytest.raises(ValidationError):
        PublicProduct.model_validate(payload)
