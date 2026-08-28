"""Pure validation and hashing rules for source ingestion."""

import hashlib
import json
import unicodedata
from typing import Any


def normalize_digits(value: str) -> str:
    """Convert Unicode decimal digits to ASCII and reject other characters."""

    normalized: list[str] = []
    for character in value.strip():
        try:
            normalized.append(str(unicodedata.decimal(character)))
        except (TypeError, ValueError) as error:
            raise ValueError("barcode must contain only decimal digits") from error
    return "".join(normalized)


def has_valid_gtin_checksum(barcode: str) -> bool:
    """Validate the final check digit for GTIN-8/12/13/14."""

    if len(barcode) not in {8, 12, 13, 14} or not barcode.isascii() or not barcode.isdigit():
        return False
    digits = [int(character) for character in barcode]
    weighted_sum = sum(
        digit * (3 if offset % 2 == 0 else 1) for offset, digit in enumerate(reversed(digits[:-1]))
    )
    expected = (10 - (weighted_sum % 10)) % 10
    return digits[-1] == expected


def normalize_barcode(value: str) -> str:
    """Normalize a source barcode and enforce the GTIN checksum."""

    normalized = normalize_digits(value)
    if not has_valid_gtin_checksum(normalized):
        raise ValueError("barcode must be a valid GTIN-8/12/13/14")
    return normalized


def validate_name(value: str) -> str:
    """Validate a source name while returning the original value for raw storage."""

    if any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError("name must not contain control characters")
    cleaned = " ".join(value.split())
    if not 1 <= len(cleaned) <= 255:
        raise ValueError("name must contain between 1 and 255 characters")
    return value


def canonical_payload_hash(payload: Any) -> str:
    """Hash JSON semantics so harmless whitespace or key order changes do not conflict."""

    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
