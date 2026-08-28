"""Unit tests for pure ingest normalization rules."""

import pytest

from packages.domain.ingest import (
    canonical_payload_hash,
    has_valid_gtin_checksum,
    normalize_barcode,
    normalize_digits,
)


def test_example_barcode_has_valid_gtin_checksum() -> None:
    assert has_valid_gtin_checksum("4850000000007")


def test_unicode_digits_are_normalized_without_losing_leading_zero() -> None:
    assert normalize_digits("٠٤٨٥٠٠٠٠٠٠٠٠٠٧") == "04850000000007"


def test_invalid_gtin_checksum_is_rejected() -> None:
    with pytest.raises(ValueError, match="valid GTIN"):
        normalize_barcode("4850000000001")


def test_payload_hash_is_independent_of_key_order() -> None:
    assert canonical_payload_hash({"a": 1, "b": 2}) == canonical_payload_hash({"b": 2, "a": 1})
