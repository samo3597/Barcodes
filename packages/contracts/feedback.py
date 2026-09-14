"""Tenant feedback and incremental change-feed contracts."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, Field, TypeAdapter, field_validator, model_validator

from packages.contracts.common import StrictContract
from packages.contracts.product import Barcode, PublicProduct
from packages.domain.ingest import normalize_barcode

FeedbackAction = Literal["accepted", "corrected", "rejected"]
FeedbackFieldName = Literal["name", "image_url", "atg_code", "vat", "is_weighted", "category_id"]


class FeedbackFieldChange(StrictContract):
    """Client-observed and operator-corrected values for one public field."""

    suggested: Any
    corrected: Any


class FeedbackRequest(StrictContract):
    barcode: Barcode
    product_version: int = Field(ge=1)
    action: FeedbackAction
    operator_ref: str | None = Field(default=None, min_length=1, max_length=255)
    fields: dict[FeedbackFieldName, FeedbackFieldChange] = Field(default_factory=dict)
    client_created_at: datetime

    @field_validator("barcode")
    @classmethod
    def validate_barcode_checksum(cls, value: str) -> str:
        return normalize_barcode(value)

    @field_validator("client_created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("client_created_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_feedback_fields(self) -> "FeedbackRequest":
        if self.action == "corrected" and not self.fields:
            raise ValueError("corrected feedback requires at least one field")
        if self.action != "corrected" and self.fields:
            raise ValueError("fields are allowed only for corrected feedback")
        for name, change in self.fields.items():
            _validate_field_value(name, change.suggested, "suggested")
            _validate_field_value(name, change.corrected, "corrected")
        return self


def _validate_field_value(name: str, value: Any, side: str) -> None:
    label = f"{name}.{side}"
    if name in {"vat", "is_weighted"}:
        if type(value) is not bool:
            raise ValueError(f"{label} must be a JSON boolean")
        return
    if name == "image_url":
        if value is not None:
            TypeAdapter(AnyHttpUrl).validate_python(value)
        return
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    if name == "name" and not 1 <= len(value.strip()) <= 255:
        raise ValueError(f"{label} must contain between 1 and 255 characters")
    if name == "atg_code" and (len(value) != 4 or not value.isascii() or not value.isdigit()):
        raise ValueError(f"{label} must contain exactly four ASCII digits")
    if name == "category_id" and not 1 <= len(value) <= 100:
        raise ValueError(f"{label} must contain between 1 and 100 characters")


class FeedbackResponse(StrictContract):
    event_id: UUID
    status: Literal["accepted"] = "accepted"
    duplicate_request: bool
    request_id: str


class ChangeItem(StrictContract):
    change_id: int = Field(ge=1)
    type: Literal["upsert", "disabled"]
    barcode: Barcode
    version: int = Field(ge=1)
    changed_at: datetime
    data: PublicProduct | None = None


class ChangesResponse(StrictContract):
    changes: list[ChangeItem]
    next_cursor: str
    has_more: bool
    request_id: str
