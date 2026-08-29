"""Unit tests for strict source payload validation."""

import pytest
from pydantic import ValidationError

from packages.contracts import IngestBatchRequest


def valid_payload() -> dict[str, object]:
    return {
        "external_batch_id": "export-001",
        "items": [
            {
                "source_record_id": "item-1",
                "barcode": "4850000000007",
                "name": "Թթվասեր 20 տոկոս 800գ",
                "image_url": "https://source.example/item-1.jpg",
                "atg_code": "0403",
                "vat": True,
                "is_weighted": False,
                "source_updated_at": "2026-08-25T08:00:00+04:00",
                "attributes": {"brand": "Example"},
            }
        ],
    }


def test_contract_preserves_raw_text_values() -> None:
    request = IngestBatchRequest.model_validate(valid_payload())

    assert request.items[0].barcode == "4850000000007"
    assert request.items[0].image_url == "https://source.example/item-1.jpg"
    assert request.items[0].source_updated_at == "2026-08-25T08:00:00+04:00"


@pytest.mark.parametrize("field", ["vat", "is_weighted"])
@pytest.mark.parametrize("value", [1, 0, "true", "false"])
def test_contract_rejects_boolean_coercion(field: str, value: object) -> None:
    payload = valid_payload()
    items = payload["items"]
    assert isinstance(items, list)
    item = items[0]
    assert isinstance(item, dict)
    item[field] = value

    with pytest.raises(ValidationError):
        IngestBatchRequest.model_validate(payload)


def test_contract_rejects_more_than_one_thousand_items() -> None:
    payload = valid_payload()
    payload["items"] = [valid_payload()["items"][0]] * 1001  # type: ignore[index]

    with pytest.raises(ValidationError):
        IngestBatchRequest.model_validate(payload)


def test_contract_requires_timezone() -> None:
    payload = valid_payload()
    items = payload["items"]
    assert isinstance(items, list)
    item = items[0]
    assert isinstance(item, dict)
    item["source_updated_at"] = "2026-08-25T08:00:00"

    with pytest.raises(ValidationError, match="timezone"):
        IngestBatchRequest.model_validate(payload)


def test_contract_rejects_duplicate_source_record_ids() -> None:
    payload = valid_payload()
    items = payload["items"]
    assert isinstance(items, list)
    first = items[0]
    assert isinstance(first, dict)
    items.append(dict(first))

    with pytest.raises(ValidationError, match="unique"):
        IngestBatchRequest.model_validate(payload)
