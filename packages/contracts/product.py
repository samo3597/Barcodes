"""The public product contract shared by Server 1 and Server 2."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, Field, StringConstraints, field_validator

from packages.contracts.common import StrictContract
from packages.domain.ingest import normalize_barcode

Barcode = Annotated[str, StringConstraints(pattern=r"^[0-9]{8,14}$")]
AtgCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}$")]


class PublicProduct(StrictContract):
    """Versioned product representation exposed to tenants."""

    barcode: Barcode
    name: str = Field(min_length=1, max_length=255)
    image_url: AnyHttpUrl | None = None
    atg_code: AtgCode
    vat: bool
    is_weighted: bool
    category_id: str = Field(min_length=1, max_length=100)
    version: int = Field(ge=1)
    quality_status: Literal["ai_processed", "source_complete", "processing_failed", "disabled"]
    updated_at: datetime

    @field_validator("barcode")
    @classmethod
    def validate_barcode_checksum(cls, value: str) -> str:
        """Reject structurally valid GTINs whose check digit is incorrect."""

        normalize_barcode(value)
        return value

    @field_validator("vat", "is_weighted", mode="before")
    @classmethod
    def reject_non_boolean_values(cls, value: object) -> object:
        """Pydantic normally coerces 0/1 and strings; the public contract must not."""

        if type(value) is not bool:
            raise ValueError("value must be a JSON boolean")
        return value
