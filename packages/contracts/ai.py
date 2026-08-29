"""Versioned contracts exchanged with AI provider adapters."""

from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from packages.contracts.common import StrictContract
from packages.domain.ingest import normalize_barcode, validate_name


class AIRequest(StrictContract):
    """One normalized, immutable candidate submitted to a provider."""

    candidate_id: UUID
    barcode: str
    prompt_version: str = Field(min_length=1, max_length=50)
    input_data: dict[str, Any]
    repair_response: dict[str, Any] | None = None

    @field_validator("barcode")
    @classmethod
    def validate_barcode(cls, value: str) -> str:
        return normalize_barcode(value)


class AITextValue(StrictContract):
    """Text value accompanied by the provider's confidence estimate."""

    value: str = Field(min_length=1, max_length=255)
    confidence: float = Field(ge=0, le=1)


class AIBooleanValue(StrictContract):
    """Strict boolean value accompanied by confidence."""

    value: bool
    confidence: float = Field(ge=0, le=1)

    @field_validator("value", mode="before")
    @classmethod
    def reject_non_boolean_values(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("value must be a JSON boolean")
        return value


class AIProductResult(StrictContract):
    """Structured result required before canonical publication can begin."""

    barcode: str
    name: AITextValue
    atg_code: AITextValue
    vat: AIBooleanValue
    is_weighted: AIBooleanValue
    category_id: AITextValue
    warnings: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("barcode")
    @classmethod
    def validate_barcode(cls, value: str) -> str:
        return normalize_barcode(value)

    @field_validator("name")
    @classmethod
    def validate_product_name(cls, value: AITextValue) -> AITextValue:
        validate_name(value.value)
        return value

    @field_validator("atg_code")
    @classmethod
    def validate_atg_code(cls, value: AITextValue) -> AITextValue:
        if len(value.value) != 4 or not value.value.isascii() or not value.value.isdigit():
            raise ValueError("atg_code must contain exactly four ASCII digits")
        return value

    @field_validator("category_id")
    @classmethod
    def validate_category_id(cls, value: AITextValue) -> AITextValue:
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789._-")
        if value.value[0] not in allowed or any(
            character not in allowed for character in value.value
        ):
            raise ValueError("category_id must use lowercase ASCII slug characters")
        return value
