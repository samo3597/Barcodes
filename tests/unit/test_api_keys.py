"""Unit tests for one-time source API keys."""

from packages.domain.api_keys import (
    extract_key_prefix,
    generate_source_api_key,
    verify_source_api_key,
)


def test_generated_key_can_be_verified_without_storing_plaintext() -> None:
    generated = generate_source_api_key()

    assert extract_key_prefix(generated.raw_key) == generated.prefix
    assert generated.raw_key not in generated.encoded_hash
    assert verify_source_api_key(generated.raw_key, generated.encoded_hash)


def test_wrong_key_is_rejected() -> None:
    generated = generate_source_api_key()

    assert not verify_source_api_key(f"{generated.raw_key}x", generated.encoded_hash)


def test_malformed_key_is_rejected_before_database_lookup() -> None:
    assert extract_key_prefix("not-a-source-key") is None
