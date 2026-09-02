"""Feedback request rules keep corrections safe and explicit."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from packages.contracts import FeedbackRequest

BARCODE = "4850000000014"


def payload() -> dict[str, object]:
    return {
        "barcode": BARCODE,
        "product_version": 7,
        "action": "corrected",
        "operator_ref": "operator-12",
        "fields": {
            "atg_code": {"suggested": "0403", "corrected": "1901"},
            "vat": {"suggested": True, "corrected": False},
        },
        "client_created_at": datetime.now(UTC),
    }


def test_corrected_feedback_accepts_only_mutable_typed_fields() -> None:
    result = FeedbackRequest.model_validate(payload())
    assert set(result.fields) == {"atg_code", "vat"}

    invalid = payload()
    invalid["fields"] = {"version": {"suggested": 7, "corrected": 8}}
    with pytest.raises(ValidationError):
        FeedbackRequest.model_validate(invalid)


@pytest.mark.parametrize(
    ("action", "fields"),
    [
        ("corrected", {}),
        ("accepted", {"vat": {"suggested": True, "corrected": False}}),
    ],
)
def test_action_and_fields_must_agree(action: str, fields: dict[str, object]) -> None:
    invalid = payload()
    invalid.update(action=action, fields=fields)
    with pytest.raises(ValidationError):
        FeedbackRequest.model_validate(invalid)


def test_feedback_requires_timezone_and_strict_field_values() -> None:
    no_timezone = payload()
    no_timezone["client_created_at"] = datetime.now()
    with pytest.raises(ValidationError):
        FeedbackRequest.model_validate(no_timezone)

    wrong_boolean = payload()
    wrong_boolean["fields"] = {"vat": {"suggested": 1, "corrected": 0}}
    with pytest.raises(ValidationError):
        FeedbackRequest.model_validate(wrong_boolean)
