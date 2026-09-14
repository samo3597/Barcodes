"""Signed change cursor behavior."""

from uuid import uuid4

import pytest

from packages.domain.change_cursor import (
    InvalidCursorError,
    decode_change_cursor,
    encode_change_cursor,
)

SECRET = "unit-test-cursor-secret"


def test_cursor_round_trip_is_tenant_bound() -> None:
    tenant_id = uuid4()
    cursor = encode_change_cursor(42, tenant_id, SECRET)

    assert decode_change_cursor(cursor, tenant_id, SECRET) == 42
    with pytest.raises(InvalidCursorError):
        decode_change_cursor(cursor, uuid4(), SECRET)


def test_cursor_rejects_tampering_and_malformed_values() -> None:
    tenant_id = uuid4()
    cursor = encode_change_cursor(42, tenant_id, SECRET)
    payload, signature = cursor.split(".")

    with pytest.raises(InvalidCursorError):
        decode_change_cursor(f"{payload}x.{signature}", tenant_id, SECRET)
    with pytest.raises(InvalidCursorError):
        decode_change_cursor("not-a-cursor", tenant_id, SECRET)
