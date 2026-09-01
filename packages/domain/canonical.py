"""Pure canonical-product versioning rules."""

from typing import Any, Literal

from pydantic import AnyHttpUrl, Field, StrictBool, field_validator

from packages.contracts.common import StrictContract
from packages.domain.ingest import canonical_payload_hash, normalize_barcode


class CanonicalFields(StrictContract):
    """Publishable fields whose semantic changes create a new version."""

    barcode: str = Field(min_length=8, max_length=14)
    name: str = Field(min_length=1, max_length=255)
    image_url: AnyHttpUrl | None = None
    atg_code: str = Field(pattern=r"^[0-9]{4}$")
    vat: StrictBool
    is_weighted: StrictBool
    category_id: str = Field(min_length=1, max_length=100)
    quality_status: Literal["ai_processed", "source_complete", "processing_failed", "disabled"]

    @field_validator("barcode")
    @classmethod
    def validate_barcode(cls, value: str) -> str:
        return normalize_barcode(value)


def canonical_hash(fields: CanonicalFields) -> str:
    """Return a stable hash excluding version and timestamps."""

    return canonical_payload_hash(fields.model_dump(mode="json"))


def changed_fields(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Describe only changed publishable fields for audit and interviews."""

    before = previous or {}
    return {
        key: {"old": before.get(key), "new": value}
        for key, value in current.items()
        if before.get(key) != value
    }
