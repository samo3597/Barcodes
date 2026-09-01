"""Contracts for source batch ingestion and status queries."""

from typing import Any, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, Field, TypeAdapter, field_validator

from packages.contracts.common import StrictContract
from packages.domain.ingest import normalize_barcode, validate_name


class IngestBatchItem(StrictContract):
    """One raw source record accepted for asynchronous processing."""

    source_record_id: str = Field(min_length=1, max_length=255)
    barcode: str
    name: str | None = None
    image_url: str | None = None
    atg_code: str | None = None
    vat: bool | None = None
    is_weighted: bool | None = None
    category: str | None = Field(default=None, max_length=255)
    source_updated_at: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("barcode")
    @classmethod
    def validate_barcode(cls, value: str) -> str:
        normalize_barcode(value)
        return value

    @field_validator("name")
    @classmethod
    def validate_optional_name(cls, value: str | None) -> str | None:
        return validate_name(value) if value is not None else None

    @field_validator("atg_code")
    @classmethod
    def validate_optional_atg(cls, value: str | None) -> str | None:
        if value is not None and (len(value) != 4 or not value.isascii() or not value.isdigit()):
            raise ValueError("atg_code must contain exactly four ASCII digits")
        return value

    @field_validator("image_url")
    @classmethod
    def validate_optional_image_url(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = TypeAdapter(AnyHttpUrl).validate_python(value)
            if parsed.scheme not in {"http", "https"}:
                raise ValueError("image_url must use http or https")
        return value

    @field_validator("source_updated_at")
    @classmethod
    def require_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            from datetime import datetime

            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("source_updated_at must include a timezone")
        return value

    @field_validator("vat", "is_weighted", mode="before")
    @classmethod
    def reject_non_boolean_values(cls, value: object) -> object:
        if value is not None and type(value) is not bool:
            raise ValueError("value must be a JSON boolean")
        return value


class IngestBatchRequest(StrictContract):
    """At most 1,000 source records accepted under one idempotency key."""

    external_batch_id: str | None = Field(default=None, min_length=1, max_length=200)
    items: list[IngestBatchItem] = Field(min_length=1, max_length=1000)


class BatchAcceptedResponse(StrictContract):
    """Immediate acknowledgement returned before heavy processing starts."""

    batch_id: UUID
    status: Literal["accepted", "processing", "completed", "failed"]
    received_items: int = Field(ge=0)
    duplicate_request: bool


class BatchStatusResponse(StrictContract):
    """Processing counters visible only to the owning source."""

    batch_id: UUID
    status: Literal["accepted", "processing", "completed", "failed"]
    received: int = Field(ge=0)
    validated: int = Field(ge=0)
    rejected: int = Field(ge=0)
    ai_pending: int = Field(ge=0)
    published: int = Field(ge=0)
    failed: int = Field(ge=0)
